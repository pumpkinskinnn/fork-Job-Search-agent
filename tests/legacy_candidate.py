"""Keep the original BSc-only regressions independent of live candidate settings."""

from contextlib import ExitStack
import unittest
from unittest.mock import patch

from ai import job_scorer
from jobs import availability_filter, education_filter, graduation_filter, student_filter


class BscCandidateTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        stack = self.enterContext(ExitStack())
        profile = dict(job_scorer.USER_PROFILE, education="BSc Chemistry, First-Class Honours",
                       highest_completed_education="bachelors", current_education="",
                       current_education_status="", graduation_year=2026, available_from="")
        for module, name, value in (
            (education_filter, "MAX_EDUCATION", "bachelors"),
            (education_filter, "CURRENT_EDUCATION", ""),
            (education_filter, "CURRENT_EDUCATION_STATUS", ""),
            (education_filter, "USER_PROFILE", profile),
            (student_filter, "CURRENT_EDUCATION", ""),
            (student_filter, "CURRENT_EDUCATION_STATUS", ""),
            (availability_filter, "CANDIDATE_AVAILABLE_FROM", ""),
            (graduation_filter, "CANDIDATE_GRADUATION_YEAR", 2026),
            (job_scorer, "USER_PROFILE", profile),
        ):
            stack.enter_context(patch.object(module, name, value))
