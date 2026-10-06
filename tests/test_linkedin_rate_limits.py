import unittest
from collections import deque
from unittest.mock import Mock, patch

from jobs import linkedin_client


class LinkedInRateLimitTests(unittest.TestCase):
    def setUp(self):
        for name, value in (
            ("_request_times", deque()), ("_last_request_at", 0.0), ("_pause_until", 0.0),
            ("_consecutive_blocks", 0), ("_cycle_limited", False), ("_cycle_requests", 0),
        ):
            patcher = patch.object(linkedin_client, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_429_stops_cycle_and_prevents_another_http_request(self):
        response = Mock(status_code=429, text="Too many requests", headers={"Retry-After": "30"})
        session = Mock()
        session.get.return_value = response
        with patch.object(linkedin_client, "get_session", return_value=session), \
             patch.object(linkedin_client.time, "monotonic", return_value=100):
            self.assertIsNone(linkedin_client.linkedin_get("https://www.linkedin.com/test"))
            self.assertTrue(linkedin_client.linkedin_is_limited())
            self.assertIsNone(linkedin_client.linkedin_get("https://www.linkedin.com/test"))
        self.assertEqual(session.get.call_count, 1)
        self.assertEqual(linkedin_client._pause_until, 130)

    def test_minimum_delay_is_still_enforced(self):
        linkedin_client._last_request_at = 100
        with patch.object(linkedin_client.time, "monotonic", side_effect=[101, 106]), \
             patch.object(linkedin_client.time, "sleep") as sleep, \
             patch.object(linkedin_client, "LINKEDIN_MIN_DELAY_SECONDS", 6):
            self.assertTrue(linkedin_client._wait_for_slot())
        sleep.assert_called_once_with(5)

    def test_hourly_and_cycle_budgets_still_stop_requests(self):
        linkedin_client._request_times = deque([90] * linkedin_client.LINKEDIN_MAX_REQUESTS_PER_HOUR)
        with patch.object(linkedin_client.time, "monotonic", return_value=200):
            self.assertFalse(linkedin_client._wait_for_slot())
        self.assertTrue(linkedin_client._cycle_limited)
        linkedin_client._cycle_limited = False
        linkedin_client._request_times.clear()
        linkedin_client._cycle_requests = linkedin_client._MAX_REQUESTS_PER_CYCLE
        self.assertFalse(linkedin_client._wait_for_slot())


if __name__ == "__main__":
    unittest.main()
