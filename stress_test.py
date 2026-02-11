#!/usr/bin/env python3
"""Stress Test for Mail Agent Pipeline.

This script simulates high concurrency email processing to validate
system stability, rate limiting, and error handling under load.

Usage:
    python stress_test.py [--emails N] [--concurrency M] [--mock-latency S]

Options:
    --emails N          Number of mock emails to generate (default: 50)
    --concurrency M     Number of concurrent workers (default: 10)
    --mock-latency S    Simulated Gemini API latency in seconds (default: 0.5)
    --simulate-429      Simulate 429 errors at a given rate (0.0-1.0, default: 0.1)
"""

import argparse
import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from mail_agent.logger import get_logger

logger = get_logger(__name__)


def generate_mock_email(email_id: int) -> Dict[str, Any]:
    """Generate a mock email for testing."""
    categories = ["Work", "Personal", "School", "Marketing", "Newsletter", "Shopping"]
    priorities = ["Critical", "High", "Normal", "Low", "Ignore"]
    
    return {
        "id": f"mock-email-{email_id}",
        "provider": "gmail",
        "account_id": "stress-test",
        "subject": f"Test Email #{email_id} - {random.choice(['Meeting', 'Invoice', 'Newsletter', 'Promo'])}",
        "from": f"sender{email_id}@example.com",
        "date": datetime.now(timezone.utc).isoformat(),
        "body": f"This is the body of test email {email_id}. " * random.randint(5, 20),
        "thread_id": f"thread-{email_id}",
        "_expected_category": random.choice(categories),
        "_expected_priority": random.choice(priorities),
    }


class StressTestRunner:
    """Runs stress tests on the Mail Agent pipeline."""

    def __init__(
        self,
        num_emails: int = 50,
        concurrency: int = 10,
        mock_latency: float = 0.5,
        simulate_429_rate: float = 0.1,
    ):
        self.num_emails = num_emails
        self.concurrency = concurrency
        self.mock_latency = mock_latency
        self.simulate_429_rate = simulate_429_rate
        
        # Metrics
        self.successful = 0
        self.failed = 0
        self.rate_limited = 0
        self.total_time = 0.0
        self.processing_times: List[float] = []

    async def mock_analyze(self, email_data: Dict[str, Any]) -> Dict[str, Any]:
        """Mock email analysis with simulated latency and errors."""
        # Simulate network latency
        await asyncio.sleep(self.mock_latency + random.uniform(0, 0.3))
        
        # Simulate 429 errors
        if random.random() < self.simulate_429_rate:
            self.rate_limited += 1
            raise Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded")
        
        # Return mock analysis result
        return {
            "category": email_data.get("_expected_category", "Personal"),
            "priority": email_data.get("_expected_priority", "Normal"),
            "summary": f"Mock summary for {email_data['id']}",
            "required_tools": [],
        }

    async def process_email(self, email: Dict[str, Any], semaphore: asyncio.Semaphore) -> bool:
        """Process a single email with concurrency control."""
        async with semaphore:
            start_time = time.time()
            try:
                # Simulate the analysis pipeline
                result = await self.mock_analyze(email)
                
                # Simulate post-processing (tagging, etc.)
                await asyncio.sleep(0.05)
                
                elapsed = time.time() - start_time
                self.processing_times.append(elapsed)
                self.successful += 1
                return True
                
            except Exception as e:
                self.failed += 1
                logger.warning(f"Email {email['id']} failed: {e}")
                return False

    async def run(self) -> Dict[str, Any]:
        """Run the stress test."""
        logger.info("=" * 60)
        logger.info("STRESS TEST STARTED")
        logger.info(f"Emails: {self.num_emails}")
        logger.info(f"Concurrency: {self.concurrency}")
        logger.info(f"Mock Latency: {self.mock_latency}s")
        logger.info(f"429 Error Rate: {self.simulate_429_rate * 100}%")
        logger.info("=" * 60)
        
        # Generate mock emails
        emails = [generate_mock_email(i) for i in range(self.num_emails)]
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.concurrency)
        
        # Run all email processing tasks
        start_time = time.time()
        tasks = [self.process_email(email, semaphore) for email in emails]
        await asyncio.gather(*tasks, return_exceptions=True)
        self.total_time = time.time() - start_time
        
        # Calculate metrics
        avg_time = sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0
        throughput = self.num_emails / self.total_time if self.total_time > 0 else 0
        
        results = {
            "total_emails": self.num_emails,
            "successful": self.successful,
            "failed": self.failed,
            "rate_limited": self.rate_limited,
            "total_time_seconds": round(self.total_time, 2),
            "avg_processing_time_seconds": round(avg_time, 3),
            "throughput_per_second": round(throughput, 2),
            "success_rate": round(self.successful / self.num_emails * 100, 1),
        }
        
        # Print results
        logger.info("=" * 60)
        logger.info("STRESS TEST COMPLETE")
        logger.info(f"Total Time: {results['total_time_seconds']}s")
        logger.info(f"Successful: {results['successful']}/{results['total_emails']} ({results['success_rate']}%)")
        logger.info(f"Failed: {results['failed']}")
        logger.info(f"Rate Limited: {results['rate_limited']}")
        logger.info(f"Avg Processing Time: {results['avg_processing_time_seconds']}s")
        logger.info(f"Throughput: {results['throughput_per_second']} emails/sec")
        logger.info("=" * 60)
        
        return results


async def main():
    parser = argparse.ArgumentParser(description="Mail Agent Stress Test")
    parser.add_argument("--emails", type=int, default=50, help="Number of mock emails")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--mock-latency", type=float, default=0.5, help="Simulated API latency")
    parser.add_argument("--simulate-429", type=float, default=0.1, help="429 error rate (0.0-1.0)")
    args = parser.parse_args()
    
    runner = StressTestRunner(
        num_emails=args.emails,
        concurrency=args.concurrency,
        mock_latency=args.mock_latency,
        simulate_429_rate=args.simulate_429,
    )
    
    results = await runner.run()
    
    # Exit with error code if success rate is too low
    if results["success_rate"] < 80:
        logger.error("STRESS TEST FAILED: Success rate below 80%")
        sys.exit(1)
    else:
        logger.info("STRESS TEST PASSED")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
