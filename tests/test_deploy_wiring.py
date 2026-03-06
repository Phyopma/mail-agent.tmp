from pathlib import Path
import unittest


class DeployWiringTests(unittest.TestCase):
    def test_deploy_script_includes_trigger_and_watch_resources(self):
        deploy_script = Path("deploy.sh").read_text(encoding="utf-8")

        self.assertIn("TRIGGER_SERVICE_NAME", deploy_script)
        self.assertIn("TRIGGER_QUEUE_NAME", deploy_script)
        self.assertIn("WATCH_JOB_NAME", deploy_script)
        self.assertIn("mail_agent.trigger_service", deploy_script)
        self.assertIn("mail_agent.main,--renew-watches", deploy_script)
        self.assertIn("MAIL_AGENT_TRIGGER_SERVICE_URL", deploy_script)
        self.assertIn("gcloud pubsub subscriptions", deploy_script)
        self.assertIn("gcloud tasks queues", deploy_script)
        self.assertIn("gmail-api-push@system.gserviceaccount.com", deploy_script)
        self.assertIn("roles/cloudtasks.enqueuer", deploy_script)
        self.assertIn("roles/run.developer", deploy_script)
        self.assertIn("TRIGGER_SHARED_SECRET", deploy_script)
        self.assertIn("gcloud run jobs execute \"$WATCH_JOB_NAME\"", deploy_script)


if __name__ == "__main__":
    unittest.main()
