"""Offline regressions for placement, natural-language degrees and JD budgets."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch

import config
from ai import job_scorer
from ai.job_evidence import EvidenceBudgetError, JOB_EVIDENCE_CHAR_LIMIT, select_job_evidence
from jobs import career_fetcher, contract_filter, education_filter, job_fetcher, location_filter
from jobs.profile_filter import pre_description_matches, profile_matches
from jobs.student_filter import student_matches


def job(description="", **fields):
    return {"title": "Graduate Battery Scientist", "company": "Example Materials",
            "location": "London, United Kingdom", "description": description, **fields}


ARUP_JD = Path(__file__).parent / "fixtures" / "arup_graduate_process_engineer_energy.txt"
STUDENT = "Must be returning to university after the placement."
PLACEMENT = "12 month industrial placement."
STANTEC = ("At Stantec, we value your potential over past experience. "
           "Along with a master’s degree in Geotechnical Engineering, "
           "and a keen interest in the energy transition, you will also be: an analytical thinker.")


class SecondLiveEligibilityTests(unittest.TestCase):
    def setUp(self):
        for module, name, value in (
            (education_filter, "FILTER_BY_EDUCATION", True),
            (education_filter, "MAX_EDUCATION", "bachelors"),
            (contract_filter, "REJECT_12_MONTH_CONTRACT", True),
            (location_filter, "FILTER_BY_LOCATION", True),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_returning_to_university_required_rejected(self):
        self.assertFalse(student_matches(job(STUDENT)))
        self.assertFalse(pre_description_matches(job(STUDENT)))
        self.assertFalse(profile_matches(job(STUDENT)))

    def test_placement_year_student_rejected(self):
        self.assertFalse(student_matches(job("placement year student")))

    def test_all_enrolment_and_placement_wordings_rejected(self):
        for text in (
            "Currently studying for a degree in Chemistry.", "Current university student.",
            "Penultimate-year student.", "Returning to university after the placement.",
            "Eligible for an industrial placement year.", "Sandwich year.", "Year in industry.",
            "Placement year.", "Must remain enrolled.", "Student placement.", "Industrial placement.",
        ):
            with self.subTest(text=text):
                self.assertFalse(student_matches(job(text)))

    def test_students_and_graduates_welcome_kept(self):
        for text in ("graduates and students welcome", "student or graduate",
                     "Students and recent graduates welcome.", "Current university students or graduates welcome."):
            with self.subTest(text=text):
                self.assertTrue(student_matches(job(text)))

    def test_graduate_programme_kept(self):
        self.assertTrue(profile_matches(job("graduate programme")))

    def test_graduate_jobs_schemes_and_graduate_open_internships_kept(self):
        for text in ("Graduate job.", "Graduate scheme.", "Internships open to graduates.",
                     "Internship available to recent graduates.", "Graduate internship."):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_placement_title_with_explicit_graduate_alternative_kept(self):
        self.assertTrue(student_matches(job("Graduates and students welcome.", title="Student Placement")))

    def test_graduate_alternative_does_not_mask_independent_enrolment(self):
        self.assertFalse(student_matches(job("Graduates welcome. Must remain enrolled.")))

    def test_preferred_or_optional_enrolment_kept(self):
        for text in ("Currently studying preferred.", "Current university student desirable.",
                     "Preferred\nPenultimate-year student.", "Placement year not required.",
                     "Requirements\nCurrent university student preferred."):
            with self.subTest(text=text):
                self.assertTrue(student_matches(job(text)))

    def test_preference_does_not_mask_separate_enrolment_requirement(self):
        self.assertFalse(student_matches(job("Materials experience preferred. Must remain enrolled.")))

    def test_mclaren_live_placement_rejected(self):
        listing = job("This is a 12-month full-time Industrial Placement, designed for university "
                      "students undertaking a placement year as part of a relevant degree programme.\n"
                      "Currently studying for a degree in Materials Science, Materials Engineering "
                      "or other relevant degree, and on track for a 2:1 or above.")
        self.assertFalse(student_matches(listing))
        self.assertFalse(contract_filter.contract_matches(listing))
        self.assertFalse(profile_matches(listing))

    def test_cummins_live_student_placement_rejected(self):
        listing = job("This role is available to candidates who qualify for a placement year.\n"
                      "Currently studying towards a BEng or MEng degree in Mechanical Engineering, "
                      "Automotive Engineering, Physics or a related discipline.\n"
                      "Student - Cooperative/12 Month Placement")
        self.assertFalse(student_matches(listing))
        self.assertFalse(contract_filter.contract_matches(listing))

    def test_all_twelve_month_placement_wordings_rejected(self):
        for text in ("12-month placement", "12 month industrial placement", "one-year placement",
                     "placement lasting 12 months", "Placement: twelve months",
                     "Placement lasts 12 months", "12-month full-time industrial placement"):
            with self.subTest(text=text):
                self.assertFalse(contract_filter.contract_matches(job(text)))

    def test_training_durations_and_other_terms_kept(self):
        for text in ("12 months training provided", "Permanent role with 12 months training provided.",
                     "Graduate programme with one-year training.", "24-month placement", "6-month placement"):
            with self.subTest(text=text):
                self.assertTrue(contract_filter.contract_matches(job(text)))

    def test_placement_duration_rejection_obeys_existing_switch(self):
        with patch.object(contract_filter, "REJECT_12_MONTH_CONTRACT", False):
            self.assertTrue(contract_filter.contract_matches(job(PLACEMENT)))

    def test_all_natural_language_masters_requirements_rejected(self):
        for text in ("Along with a master's degree in Chemistry.",
                     "You will have a master's degree in Chemistry.",
                     "Candidates will possess a master's degree in Chemistry.",
                     "A master's degree in Chemistry is expected.",
                     "A Masters level (or equivalent) in relevant academic discipline."):
            with self.subTest(text=text):
                self.assertFalse(education_filter.education_matches(job(text)))

    def test_stantec_live_wording_rejected(self):
        self.assertFalse(education_filter.education_matches(job(STANTEC)))
        self.assertFalse(pre_description_matches(job(STANTEC)))
        self.assertFalse(profile_matches(job(STANTEC)))

    def test_masters_preferences_and_bachelors_alternatives_kept(self):
        for text in ("Master's preferred", "Master's desirable", "Bachelor's or Master's accepted",
                     "Bachelor's in Chemistry or related discipline.",
                     "You will have a Bachelor's or Master's degree in Chemistry.",
                     "Candidates will possess an MSc or BSc in Chemistry.",
                     "Along with a master's degree preferred, a bachelor's is accepted."):
            with self.subTest(text=text):
                self.assertTrue(education_filter.education_matches(job(text)))

    def test_narrative_masters_mentions_do_not_become_requirements(self):
        self.assertTrue(education_filter.education_matches(job("Our team includes master's degree holders.")))

    def test_new_barriers_rejected_before_linkedin_description_requests(self):
        for text in (STUDENT, PLACEMENT, STANTEC):
            with self.subTest(text=text), patch.object(job_fetcher, "attach_description") as attach:
                self.assertFalse(job_fetcher._is_relevant(job(text), "", config.USER_PROFILE["target_roles"]))
                attach.assert_not_called()

    def test_ats_pipeline_removes_barriers_before_detail_enrichment(self):
        accepted = job("Battery materials research; graduates welcome.")
        listings = [job(text) for text in (STUDENT, PLACEMENT, STANTEC)] + [accepted]
        with patch.object(career_fetcher, "get_career_config", return_value={"ats": "lever", "slug": "example"}), \
             patch.object(career_fetcher, "_fetch_from_ats", return_value=listings), \
             patch.object(career_fetcher, "enrich_ats_descriptions") as enrich:
            self.assertEqual(career_fetcher.fetch_career_jobs_for_company("Example"), [accepted])
        enrich.assert_called_once_with([accepted])

    def test_direct_scoring_hard_barriers_make_no_provider_or_description_call(self):
        with patch.object(job_scorer, "generate") as generate, \
             patch.object(job_scorer, "fetch_job_description") as fetch, \
             patch.object(job_scorer, "distilled_profile") as profile:
            results = job_scorer.score_jobs_batch([job(text) for text in (STUDENT, PLACEMENT, STANTEC)], persist=False)
        self.assertEqual(results, [{"score": 0}] * 3)
        generate.assert_not_called()
        fetch.assert_not_called()
        profile.assert_not_called()

    def test_mixed_scoring_only_sends_eligible_jobs_and_preserves_order(self):
        listings = [job(STUDENT, company="Blocked student"), job("Battery research.", company="Good A"),
                    job(STANTEC, company="Blocked masters"), job(PLACEMENT, company="Blocked placement"),
                    job("Materials research.", company="Good B")]
        with patch.object(job_scorer, "distilled_profile", return_value="Graduate BSc Chemistry"), \
             patch.object(job_scorer, "generate", return_value=json.dumps({"s": [82, 86]})) as generate:
            results = job_scorer.score_jobs_batch(listings, persist=False)
        self.assertEqual([r["score"] for r in results], [0, 82, 0, 0, 86])
        prompt = generate.call_args.args[1]
        self.assertIn("Good A", prompt)
        self.assertIn("Good B", prompt)
        self.assertNotIn("Blocked", prompt)
        self.assertIn("exactly 2 integers", prompt)

    def test_newly_retrieved_student_requirement_blocks_model_call(self):
        listing = job()
        def fill_description(j):
            j["description"] = STUDENT
            return STUDENT
        with patch.object(job_scorer, "fetch_job_description", side_effect=fill_description) as fetch, \
             patch.object(job_scorer, "generate") as generate:
            result = job_scorer.score_job(listing, persist=False)
        self.assertEqual(result["score"], 0)
        fetch.assert_called_once()
        generate.assert_not_called()

    def test_missing_description_only_attempted_once_before_scoring(self):
        with patch.object(job_scorer, "fetch_job_description", return_value="Job description unavailable.") as fetch, \
             patch.object(job_scorer, "distilled_profile", return_value="BSc Chemistry"), \
             patch.object(job_scorer, "generate", return_value='{"s":[90]}'):
            result = job_scorer.score_job(job(), persist=False)
        fetch.assert_called_once()
        self.assertEqual(result["score"], 60)

    def test_ambiguous_remote_can_establish_uk_eligibility_before_scoring(self):
        listing = job(location="Remote")
        def fill_description(j):
            j["description"] = "Battery research; remote work for UK-based graduates."
            return j["description"]
        with patch.object(job_scorer, "fetch_job_description", side_effect=fill_description) as fetch, \
             patch.object(job_scorer, "distilled_profile", return_value="BSc Chemistry"), \
             patch.object(job_scorer, "generate", return_value='{"s":[84]}'):
            result = job_scorer.score_job(listing, persist=False)
        fetch.assert_called_once()
        self.assertEqual(result["score"], 84)

    def test_remote_without_uk_eligibility_is_rejected_after_description(self):
        listing = job(location="Remote")
        def fill_description(j):
            j["description"] = "Battery research for recent graduates."
            return j["description"]
        with patch.object(job_scorer, "fetch_job_description", side_effect=fill_description) as fetch, \
             patch.object(job_scorer, "generate") as generate:
            result = job_scorer.score_job(listing, persist=False)
        fetch.assert_called_once()
        generate.assert_not_called()
        self.assertEqual(result["score"], 0)


class EvidenceBudgetRegressionTests(unittest.TestCase):
    def test_saved_arup_jd_fits_unchanged_budget_with_core_evidence(self):
        description = ARUP_JD.read_text(encoding="utf-8")
        self.assertGreater(len(description), JOB_EVIDENCE_CHAR_LIMIT)
        self.assertEqual(JOB_EVIDENCE_CHAR_LIMIT, 2400)
        excerpt = select_job_evidence(description)
        self.assertLessEqual(len(excerpt), 2400)
        for text in ("A Masters level (or equivalent)", "Full working rights", "No more than 12 months",
                     "Recently graduated", "unable to offer visa sponsorship", "eligible to work permanently"):
            self.assertIn(text, excerpt)
        self.assertNotIn("Profit Share", excerpt)
        self.assertNotIn("Private medical insurance", excerpt)

    def test_saved_arup_job_rejected_before_budget_or_provider_call(self):
        listing = job(ARUP_JD.read_text(encoding="utf-8"), title="Graduate Process Engineer - Energy")
        self.assertFalse(education_filter.education_matches(listing))
        with patch.object(job_scorer, "generate") as generate:
            result = job_scorer.score_job(listing, persist=False)
        self.assertEqual(result["score"], 0)
        generate.assert_not_called()

    def test_actual_eligibility_precedes_secondary_duties_and_preferences(self):
        critical = ("Bachelor's degree in Chemistry required.", STUDENT,
                    "Three years industry experience required.", "Placement lasting 12 months.",
                    "Applicants graduating in 2027 only.")
        description = ("Responsibilities\n" + "\n".join(f"Analyse materials dataset {i}." for i in range(100))
                       + "\nEligibility\n" + "\n".join(critical)
                       + "\nPreferred\n" + "\n".join(f"Experience with optional tool {i} preferred." for i in range(50)))
        excerpt = select_job_evidence(description)
        for text in critical:
            self.assertIn(text, excerpt)
        self.assertLessEqual(len(excerpt), 2400)
        self.assertLess(excerpt.index("Applicants graduating"), excerpt.index("Analyse materials"))

    def test_eligibility_context_ends_before_benefits_recruitment_and_eeo(self):
        description = ("Eligibility\nBachelor's degree in Chemistry required.\n"
                       "What we offer you\n" + "\n".join(
                           f"Permanent members of nationality group {i} receive benefits and experience our culture."
                           for i in range(100)) + "\nNext Steps\nApplications reviewed promptly.\n"
                       "Different people, shared values\nWe welcome all backgrounds regardless of nationality.")
        excerpt = select_job_evidence(description)
        self.assertIn("Bachelor's degree in Chemistry required.", excerpt)
        self.assertNotIn("Permanent members", excerpt)
        self.assertNotIn("nationality", excerpt)

    def test_misplaced_hard_requirement_is_not_lost_under_benefits(self):
        excerpt = select_job_evidence("Benefits\nCurrent university student required.\n"
                                      "Master's degree required.\nApplicants graduating in 2027 only required.")
        for text in ("Current university student", "Master's degree", "graduating in 2027"):
            self.assertIn(text, excerpt)

    def test_genuinely_oversized_critical_evidence_still_fails_closed(self):
        description = "Requirements\nBachelor's degree in Chemistry with " + "demonstrated laboratory knowledge " * 120 + "required."
        with self.assertRaises(EvidenceBudgetError):
            select_job_evidence(description)


if __name__ == "__main__":
    unittest.main()
