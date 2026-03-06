import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from mail_agent import main as main_module


class RenewWatchTests(unittest.TestCase):
    def test_renew_gmail_watches_raises_after_single_account_failure(self):
        accounts = [
            {
                "account_id": "acc-1",
                "credentials_path": "/tmp/creds-1.json",
                "token_path": "/tmp/token-1.pickle",
            },
            {
                "account_id": "acc-2",
                "credentials_path": "/tmp/creds-2.json",
                "token_path": "/tmp/token-2.pickle",
            },
        ]

        with patch.object(main_module, "load_accounts_config", return_value=accounts), patch.object(
            main_module.config,
            "get",
            side_effect=lambda key, default=None: "projects/test/topics/watch" if key == "gmail_watch_topic" else default,
        ), patch.object(main_module, "GoogleServiceManager") as manager_cls:
            manager = manager_cls.return_value
            manager.setup_gmail_watch = AsyncMock(
                side_effect=[
                    {"historyId": "101", "expiration": "999"},
                    RuntimeError("boom"),
                ]
            )

            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(main_module.renew_gmail_watches())

        self.assertIn("acc-2", str(ctx.exception))
        self.assertEqual(manager.setup_gmail_watch.await_count, 2)
        first_call = manager.setup_gmail_watch.await_args_list[0]
        self.assertEqual(first_call.kwargs["topic_name"], "projects/test/topics/watch")
        self.assertEqual(first_call.kwargs["account_id"], "acc-1")
        second_call = manager.setup_gmail_watch.await_args_list[1]
        self.assertEqual(second_call.kwargs["topic_name"], "projects/test/topics/watch")
        self.assertEqual(second_call.kwargs["account_id"], "acc-2")


if __name__ == "__main__":
    unittest.main()
