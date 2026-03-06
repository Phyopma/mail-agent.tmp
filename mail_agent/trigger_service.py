"""Cloud Run receiver for Gmail Pub/Sub triggers and debounced executions."""

from __future__ import annotations

import base64
import binascii
import json
import os
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Mapping, Optional, Tuple
from urllib.parse import urlparse

from googleapiclient.discovery import build

from mail_agent.account_loader import build_account_email_map, load_accounts_config


def _parse_rfc3339_seconds(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return None


def _is_duplicate_task_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code == 409:
        return True
    message = str(exc).lower()
    return "alreadyexists" in message or "already exists" in message or " 409" in message


class TriggerService:
    """Core logic for Gmail push debouncing and job launches."""

    def __init__(
        self,
        accounts_config: List[Dict[str, Any]],
        project_id: str,
        region: str,
        queue_name: str,
        service_url: str,
        job_name: str = "mail-agent-job",
        debounce_seconds: int = 60,
        min_execution_gap_seconds: int = 120,
        push_enabled: bool = True,
        internal_auth_token: Optional[str] = None,
        tasks_client: Any = None,
        run_client: Any = None,
        clock: Any = None,
    ) -> None:
        self.accounts_config = accounts_config
        self.account_email_map = build_account_email_map(accounts_config)
        self.project_id = project_id
        self.region = region
        self.queue_name = queue_name
        self.service_url = service_url.rstrip("/")
        self.job_name = job_name
        self.debounce_seconds = debounce_seconds
        self.min_execution_gap_seconds = min_execution_gap_seconds
        self.push_enabled = push_enabled
        self.internal_auth_token = internal_auth_token
        self.tasks_client = tasks_client or build("cloudtasks", "v2")
        self.run_client = run_client or build("run", "v2")
        self.clock = clock or time.time

    @classmethod
    def from_env(cls) -> "TriggerService":
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("PROJECT_ID") or ""
        region = os.getenv("REGION", "us-central1")
        queue_name = os.getenv("MAIL_AGENT_TRIGGER_TASKS_QUEUE", "mail-agent-trigger")
        service_url = os.getenv("MAIL_AGENT_TRIGGER_SERVICE_URL", "")
        job_name = os.getenv("MAIL_AGENT_TRIGGER_JOB_NAME", "mail-agent-job")
        debounce_seconds = int(os.getenv("MAIL_AGENT_TRIGGER_DEBOUNCE_SECONDS", "60"))
        min_execution_gap_seconds = int(os.getenv("MAIL_AGENT_TRIGGER_MIN_EXECUTION_GAP_SECONDS", "120"))
        push_enabled = os.getenv("MAIL_AGENT_PUSH_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
        internal_auth_token = os.getenv("MAIL_AGENT_TRIGGER_SHARED_SECRET")
        accounts_file = os.getenv("MAIL_AGENT_ACCOUNTS_FILE")
        return cls(
            accounts_config=load_accounts_config(accounts_file),
            project_id=project_id,
            region=region,
            queue_name=queue_name,
            service_url=service_url,
            job_name=job_name,
            debounce_seconds=debounce_seconds,
            min_execution_gap_seconds=min_execution_gap_seconds,
            push_enabled=push_enabled,
            internal_auth_token=internal_auth_token,
        )

    def handle_healthz(self) -> Tuple[int, Dict[str, Any]]:
        return 200, {"ok": True}

    def handle_pubsub_gmail(self, envelope: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        if not self.push_enabled:
            return 202, {"status": "disabled"}

        message = envelope.get("message") or {}
        encoded_data = message.get("data")
        if not encoded_data:
            return 400, {"error": "missing message.data"}

        try:
            payload = json.loads(base64.b64decode(encoded_data, validate=True).decode("utf-8"))
        except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError):
            return 400, {"error": "invalid message.data payload"}
        email_address = (payload.get("emailAddress") or "").strip().lower()
        if not email_address:
            return 400, {"error": "missing emailAddress"}
        account = self.account_email_map.get(email_address)
        if not account:
            return 202, {
                "status": "ignored",
                "reason": "unknown_account",
                "email_address": email_address,
            }

        task_name = self.enqueue_account_execution(account["account_id"])
        return 202, {
            "status": "scheduled",
            "account_id": account["account_id"],
            "task_name": task_name,
        }

    def enqueue_account_execution(self, account_id: str) -> str:
        queue_path = self._queue_path()
        if not self.service_url:
            raise ValueError("MAIL_AGENT_TRIGGER_SERVICE_URL must be set")
        schedule_time = int(self.clock()) + self.debounce_seconds
        slot_window = max(self.debounce_seconds, self.min_execution_gap_seconds, 1)
        slot = int(self.clock()) // slot_window
        task_name = f"{queue_path}/tasks/gmail-trigger-{account_id}-{slot}"
        headers = {"Content-Type": "application/json"}
        if self.internal_auth_token:
            headers["X-Mail-Agent-Internal-Token"] = self.internal_auth_token
        body = {
            "name": task_name,
            "scheduleTime": {"seconds": schedule_time},
            "httpRequest": {
                "httpMethod": "POST",
                "url": f"{self.service_url}/internal/execute/{account_id}",
                "headers": headers,
                "body": base64.b64encode(b"{}").decode("utf-8"),
            },
        }
        try:
            self.tasks_client.projects().locations().queues().tasks().create(
                parent=queue_path,
                body={"task": body},
            ).execute()
        except Exception as exc:
            if not _is_duplicate_task_error(exc):
                raise
        return task_name

    def handle_internal_execute(
        self,
        account_id: str,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Tuple[int, Dict[str, Any]]:
        if self.internal_auth_token:
            supplied_token = self._extract_internal_token(headers)
            if supplied_token != self.internal_auth_token.strip():
                return 403, {"error": "forbidden"}
        if self._run_active_or_recent(account_id):
            return 202, {
                "status": "skipped",
                "reason": "active_or_recent",
                "account_id": account_id,
            }

        execution = self._launch_job(account_id)
        return 202, {
            "status": "started",
            "account_id": account_id,
            "execution": execution,
        }

    def _queue_path(self) -> str:
        return f"projects/{self.project_id}/locations/{self.region}/queues/{self.queue_name}"

    def _job_path(self) -> str:
        return f"projects/{self.project_id}/locations/{self.region}/jobs/{self.job_name}"

    def _execution_matches_account(self, execution: Dict[str, Any], account_id: str) -> bool:
        labels = execution.get("labels") or {}
        if labels.get("account_id") == account_id:
            return True

        template = execution.get("template") or {}
        nested_template = template.get("template") or {}
        containers = nested_template.get("containers") or template.get("containers") or []
        for container in containers:
            for env_var in container.get("env", []):
                if env_var.get("name") == "MAIL_AGENT_TARGET_ACCOUNT_ID" and env_var.get("value") == account_id:
                    return True
            args = container.get("args") or []
            if account_id in args:
                return True
        return False

    def _extract_internal_token(self, headers: Optional[Mapping[str, str]]) -> Optional[str]:
        if not headers:
            return None

        header_getter = getattr(headers, "get", None)
        if callable(header_getter):
            value = header_getter("X-Mail-Agent-Internal-Token")
            if value is None:
                value = header_getter("x-mail-agent-internal-token")
            if value is not None:
                return str(value).strip()

        normalized = {str(key).lower(): str(value).strip() for key, value in headers.items()}
        return normalized.get("x-mail-agent-internal-token")

    def _run_active_or_recent(self, account_id: str) -> bool:
        now = int(self.clock())
        page_token = None

        while True:
            request = self.run_client.projects().locations().jobs().executions().list(
                parent=self._job_path(),
                pageToken=page_token,
            )
            response = request.execute()
            executions = response.get("executions", [])

            for execution in executions:
                if not self._execution_matches_account(execution, account_id):
                    continue
                if execution.get("completionTime") is None:
                    return True
                completion_seconds = _parse_rfc3339_seconds(execution.get("completionTime"))
                if completion_seconds is not None and now - completion_seconds < self.min_execution_gap_seconds:
                    return True

            page_token = response.get("nextPageToken")
            if not page_token:
                break
        return False

    def _launch_job(self, account_id: str) -> Dict[str, Any]:
        body = {
            "overrides": {
                "containerOverrides": [
                    {
                        "args": ["--process", "--account-id", account_id],
                        "env": [
                            {
                                "name": "MAIL_AGENT_TARGET_ACCOUNT_ID",
                                "value": account_id,
                            }
                        ]
                    }
                ]
            }
        }
        return self.run_client.projects().locations().jobs().run(
            name=self._job_path(),
            body=body,
        ).execute()


class TriggerRequestHandler(BaseHTTPRequestHandler):
    """Thin HTTP adapter over TriggerService."""

    service: TriggerService = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._write_json(*self.service.handle_healthz())
            return
        self._write_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length) if content_length else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(400, {"error": "invalid_json"})
            return

        if parsed.path == "/pubsub/gmail":
            self._write_json(*self.service.handle_pubsub_gmail(payload))
            return

        if parsed.path.startswith("/internal/execute/"):
            account_id = parsed.path.rsplit("/", 1)[-1]
            self._write_json(*self.service.handle_internal_execute(account_id, headers=self.headers))
            return

        self._write_json(404, {"error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _write_json(self, status_code: int, payload: Dict[str, Any]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    TriggerRequestHandler.service = TriggerService.from_env()
    server = ThreadingHTTPServer((host, port), TriggerRequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
