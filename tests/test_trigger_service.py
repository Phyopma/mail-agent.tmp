import base64
import json
import unittest

from mail_agent.trigger_service import TriggerService


class _FakeRequest:
    def __init__(self, payload=None, error=None):
        self.payload = payload or {}
        self.error = error

    def execute(self):
        if self.error:
            raise self.error
        return self.payload


class _FakeTasksClient:
    def __init__(self):
        self.created = []
        self.created_names = set()

    def projects(self):
        return self

    def locations(self):
        return self

    def queues(self):
        return self

    def tasks(self):
        return self

    def create(self, parent, body):
        task = body["task"]
        name = task["name"]
        if name in self.created_names:
            return _FakeRequest(error=Exception("AlreadyExists"))
        self.created_names.add(name)
        self.created.append({"parent": parent, "body": body})
        return _FakeRequest({"name": name})


class _FakeDuplicateError(Exception):
    status_code = 409


class _FakeRunClient:
    def __init__(self, executions=None):
        self.execution_items = executions or []
        self.run_bodies = []

    def projects(self):
        return self

    def locations(self):
        return self

    def jobs(self):
        return self

    def executions(self):
        return self

    def list(self, parent, pageToken=None):
        if pageToken == "page-2":
            return _FakeRequest({"executions": self.execution_items[1:]})
        if len(self.execution_items) > 1:
            return _FakeRequest({"executions": self.execution_items[:1], "nextPageToken": "page-2"})
        return _FakeRequest({"executions": self.execution_items})

    def run(self, name, body):
        self.run_bodies.append({"name": name, "body": body})
        return _FakeRequest({"name": f"{name}/executions/exec-1"})


class TriggerServiceTests(unittest.TestCase):
    def _service(self, tasks_client=None, run_client=None, clock=None):
        return TriggerService(
            accounts_config=[{"account_id": "acc-1", "email": "user@example.com"}],
            project_id="test-project",
            region="us-central1",
            queue_name="mail-agent-trigger",
            service_url="https://trigger.example.com",
            debounce_seconds=60,
            min_execution_gap_seconds=120,
            tasks_client=tasks_client or _FakeTasksClient(),
            run_client=run_client or _FakeRunClient(),
            clock=clock or (lambda: 120),
            internal_auth_token="shared-secret",
        )

    def test_pubsub_notification_schedules_account_execution(self):
        tasks_client = _FakeTasksClient()
        service = self._service(tasks_client=tasks_client)
        envelope = {
            "message": {
                "data": base64.b64encode(
                    json.dumps({"emailAddress": "user@example.com", "historyId": "123"}).encode("utf-8")
                ).decode("utf-8")
            }
        }

        status, payload = service.handle_pubsub_gmail(envelope)

        self.assertEqual(status, 202)
        self.assertEqual(payload["status"], "scheduled")
        self.assertEqual(payload["account_id"], "acc-1")
        self.assertEqual(len(tasks_client.created), 1)
        self.assertEqual(
            tasks_client.created[0]["body"]["task"]["httpRequest"]["url"],
            "https://trigger.example.com/internal/execute/acc-1",
        )
        self.assertEqual(
            tasks_client.created[0]["body"]["task"]["httpRequest"]["headers"]["X-Mail-Agent-Internal-Token"],
            "shared-secret",
        )

    def test_pubsub_debounce_reuses_same_task_name_within_window(self):
        tasks_client = _FakeTasksClient()
        service = self._service(tasks_client=tasks_client, clock=lambda: 180)

        first = service.enqueue_account_execution("acc-1")
        second = service.enqueue_account_execution("acc-1")

        self.assertEqual(first, second)
        self.assertEqual(len(tasks_client.created), 1)

    def test_pubsub_invalid_payload_returns_bad_request(self):
        service = self._service()
        envelope = {"message": {"data": "not-base64"}}

        status, payload = service.handle_pubsub_gmail(envelope)

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "invalid message.data payload")

    def test_internal_execute_skips_recent_execution_for_same_account(self):
        run_client = _FakeRunClient(
            executions=[
                {
                    "completionTime": "1970-01-01T00:15:30Z",
                    "template": {
                        "template": {
                            "containers": [
                                {
                                    "env": [
                                        {
                                            "name": "MAIL_AGENT_TARGET_ACCOUNT_ID",
                                            "value": "acc-1",
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                }
            ]
        )
        service = self._service(run_client=run_client, clock=lambda: 1000)

        status, payload = service.handle_internal_execute(
            "acc-1",
            headers={"X-Mail-Agent-Internal-Token": "shared-secret"},
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload["status"], "skipped")
        self.assertEqual(run_client.run_bodies, [])

    def test_internal_execute_starts_job_when_execution_gap_has_elapsed(self):
        run_client = _FakeRunClient(
            executions=[
                {
                    "completionTime": "1970-01-01T00:10:00Z",
                    "template": {
                        "template": {
                            "containers": [
                                {
                                    "env": [
                                        {
                                            "name": "MAIL_AGENT_TARGET_ACCOUNT_ID",
                                            "value": "acc-1",
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                }
            ]
        )
        service = self._service(run_client=run_client, clock=lambda: 1000)

        status, payload = service.handle_internal_execute(
            "acc-1",
            headers={"X-Mail-Agent-Internal-Token": "shared-secret"},
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload["status"], "started")
        self.assertEqual(len(run_client.run_bodies), 1)
        container_overrides = run_client.run_bodies[0]["body"]["overrides"]["containerOverrides"][0]
        self.assertEqual(
            container_overrides["env"][0],
            {"name": "MAIL_AGENT_TARGET_ACCOUNT_ID", "value": "acc-1"},
        )

    def test_internal_execute_rejects_missing_internal_token(self):
        service = self._service()

        status, payload = service.handle_internal_execute("acc-1", headers={})

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"], "forbidden")

    def test_internal_execute_accepts_case_insensitive_internal_token_header(self):
        service = self._service()

        status, payload = service.handle_internal_execute(
            "acc-1",
            headers={"x-mail-agent-internal-token": " shared-secret "},
        )

        self.assertEqual(status, 202)
        self.assertEqual(payload["status"], "started")

    def test_duplicate_task_detection_handles_http_409_style_errors(self):
        tasks_client = _FakeTasksClient()
        service = self._service(tasks_client=tasks_client, clock=lambda: 240)
        tasks_client.created_names.add("projects/test-project/locations/us-central1/queues/mail-agent-trigger/tasks/gmail-trigger-acc-1-2")
        original_create = tasks_client.create

        def create(parent, body):
            if body["task"]["name"].endswith("gmail-trigger-acc-1-2"):
                return _FakeRequest(error=_FakeDuplicateError("409 duplicate"))
            return original_create(parent, body)

        tasks_client.create = create

        task_name = service.enqueue_account_execution("acc-1")

        self.assertTrue(task_name.endswith("gmail-trigger-acc-1-2"))

    def test_enqueue_requires_configured_trigger_service_url(self):
        service = TriggerService(
            accounts_config=[{"account_id": "acc-1", "email": "user@example.com"}],
            project_id="test-project",
            region="us-central1",
            queue_name="mail-agent-trigger",
            service_url="",
            tasks_client=_FakeTasksClient(),
            run_client=_FakeRunClient(),
            clock=lambda: 120,
        )

        with self.assertRaises(ValueError):
            service.enqueue_account_execution("acc-1")


if __name__ == "__main__":
    unittest.main()
