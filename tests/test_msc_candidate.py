"""Offline regressions for an in-progress materials MSc and October availability."""

from contextlib import ExitStack
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import config
from ai import job_scorer
from ai.candidate_profile import build_candidate_profile, PROFILE_CHAR_LIMIT, PROFILE_HEADROOM_CHARS
from ai.job_evidence import select_job_evidence
from jobs import availability_filter, database, education_filter, graduation_filter, job_fetcher, job_store, student_filter
from jobs.profile_filter import profile_matches
from tests.test_candidate_profile import CV, EXPERIENCES


MODULES = ("Materials for Energy Conversion and Storage", "Nanomaterials",
           "Optoelectronic Materials", "Materials Sustainability")
YEAR_QUERIES = ("2027 graduate energy", "energy graduate scheme 2027", "2027 sustainability graduate",
                "materials graduate 2027", "graduate materials scientist 2027",
                "energy transition graduate 2027", "graduate consultant energy 2027")
MSC_PROFILE = dict(config.USER_PROFILE, highest_completed_education="bachelors", current_education="masters",
                   current_education_status="in_progress", graduation_year=2027, available_from="2027-10-01",
                   education="Completed BSc Chemistry, First-Class Honours")
MSC_CV = CV.replace("Recent BSc Chemistry graduate with First-Class Honours.",
    "Current MSc Advanced Materials Science and Engineering student at Imperial College London (2026-2027), "
    "with a First-Class Honours BSc Chemistry. Available for full-time employment from October 2027.")
MSC_CV = MSC_CV.replace("EDUCATION\n", "EDUCATION\nImperial College London\n"
    "MSc Advanced Materials Science and Engineering, 2026-2027\nIn progress; expected completion 2027\n"
    "Relevant modules:\n" + "\n".join("- " + module for module in MODULES) + "\n\n")


def job(description="", **fields):
    return {"title": "Graduate Materials Scientist", "company": "Example Materials",
            "location": "London, United Kingdom", "description": description, **fields}


class MscEligibilityTests(unittest.TestCase):
    def setUp(self):
        stack = self.enterContext(ExitStack())
        for module, name, value in (
            (education_filter, "MAX_EDUCATION", "bachelors"),
            (education_filter, "FILTER_BY_EDUCATION", True),
            (education_filter, "CURRENT_EDUCATION", "masters"),
            (education_filter, "CURRENT_EDUCATION_STATUS", "in_progress"),
            (education_filter, "CURRENT_EDUCATION_DISCIPLINE", "Advanced Materials Science and Engineering"),
            (education_filter, "USER_PROFILE", MSC_PROFILE),
            (student_filter, "CURRENT_EDUCATION", "masters"),
            (student_filter, "CURRENT_EDUCATION_STATUS", "in_progress"),
            (availability_filter, "CANDIDATE_AVAILABLE_FROM", "2027-10-01"),
            (graduation_filter, "CANDIDATE_GRADUATION_YEAR", 2027),
            (job_scorer, "USER_PROFILE", MSC_PROFILE),
        ):
            stack.enter_context(patch.object(module, name, value))

    def test_2027_graduate_energy_analyst_accepted(self):
        self.assertTrue(profile_matches(job(title="2027 Graduate Energy Analyst")))

    def test_final_year_masters_students_2027_accepted(self):
        self.assertTrue(profile_matches(job("Final-year Master's students graduating in 2027 welcome")))

    def test_masters_required_october_2027_accepted(self):
        self.assertTrue(profile_matches(job("Master's required, October 2027 start")))

    def test_january_2028_start_accepted(self):
        self.assertTrue(profile_matches(job(title="Graduate Materials Scientist, January 2028 start")))

    def test_2026_or_2027_graduates_accepted(self):
        self.assertTrue(profile_matches(job("2026 or 2027 graduates")))

    def test_2026_only_rejected(self):
        self.assertFalse(profile_matches(job("2026 graduates only")))

    def test_2028_only_rejected(self):
        self.assertFalse(profile_matches(job("2028 graduates only")))

    def test_masters_required_immediate_start_rejected(self):
        with patch.object(availability_filter, "date", wraps=date) as clock:
            clock.today.return_value = date(2026, 10, 29)
            self.assertFalse(profile_matches(job("Master's required, immediate start before MSc completion")))

    def test_must_already_hold_completed_masters_rejected(self):
        self.assertFalse(profile_matches(job("Must already hold a completed Master's degree")))

    def test_must_currently_hold_completed_masters_rejected(self):
        self.assertFalse(education_filter.education_matches(job("Must currently hold a completed Master's degree")))

    def test_september_2027_fixed_start_rejected(self):
        self.assertFalse(profile_matches(job("Start date: September 2027")))

    def test_industrial_placement_returning_to_university_rejected(self):
        self.assertFalse(profile_matches(job("Industrial placement year; must return to university afterwards")))

    def test_autumn_2027_start_kept_with_confirmation_flag(self):
        listing = job("Autumn 2027 start")
        self.assertTrue(profile_matches(listing))
        self.assertTrue(any("Confirm start date" in item for item in listing["eligibility_warnings"]))

    def test_no_start_date_kept(self):
        self.assertTrue(profile_matches(job("Research battery materials and energy storage.")))

    def test_masters_required_september_2026_rejected(self):
        listing = job("Master's required; September 2026 start")
        self.assertFalse(profile_matches(listing))
        self.assertFalse(education_filter.education_matches(listing))

    def test_compatible_materials_masters_requirement_accepted(self):
        for text in ("You will have a master's degree in Materials Science. Start date: October 2027.",
                     "Along with a master's degree in Chemistry. October 2027 start.",
                     "Candidates will possess an MSc in Materials Engineering. Start date: January 2028."):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_incompatible_masters_disciplines_rejected(self):
        for discipline in ("Finance", "Computer Science", "Mechanical Engineering", "Geotechnical Engineering"):
            with self.subTest(discipline=discipline):
                self.assertFalse(profile_matches(job(f"Master's degree in {discipline} required. October 2027 start.")))

    def test_skills_after_degree_do_not_change_required_discipline(self):
        self.assertTrue(profile_matches(job("Master's in Materials Science with Data Science skills required. October 2027 start.")))

    def test_ms_office_does_not_become_a_masters_requirement(self):
        listing = job("Requirements\nMS Office and Excel required for materials research.")
        self.assertTrue(profile_matches(listing))
        self.assertFalse(listing.get("eligibility_warnings"))
        self.assertNotIn("Qualifications:", select_job_evidence(listing["description"]))

    def test_relevant_masters_alternative_kept(self):
        self.assertTrue(profile_matches(job("Master's in Mechanical Engineering or Materials Science required. October 2027 start.")))

    def test_masters_alternative_to_phd_can_qualify_by_start(self):
        self.assertTrue(profile_matches(job("Master's or PhD in Materials Science required. October 2027 start.")))
        self.assertFalse(profile_matches(job("PhD in Materials Science required. October 2027 start.")))

    def test_completed_by_application_wording_rejected(self):
        for text in ("Master's must be completed at application time.",
                     "A master's degree must be awarded before application.",
                     "At application you must have obtained a master's degree."):
            with self.subTest(text=text):
                self.assertFalse(education_filter.education_matches(job(text)))

    def test_preferences_and_bachelors_alternatives_stay_open(self):
        for text in ("Master's in Mechanical Engineering preferred.", "Master's desirable.",
                     "Bachelor's or Master's degree accepted.", "Bachelor's in Chemistry or related discipline."):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_masters_without_start_date_kept_but_completion_needs_confirmation(self):
        listing = job("Master's in Materials Science required.")
        self.assertTrue(profile_matches(listing))
        self.assertIn("Education: MSc is in progress; confirm completion before the required start date.", listing["eligibility_warnings"])

    def test_completed_bachelors_engineering_requirement_is_not_met_by_ongoing_msc(self):
        self.assertFalse(profile_matches(job("Bachelor's in Electrical Engineering required.")))

    def test_non_degree_postgraduate_internships_are_allowed(self):
        for text in ("Internship open to current postgraduate students or graduates.",
                     "Currently studying an MSc; temporary materials internship.",
                     "Current university student required for this materials internship."):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_postgraduate_invitation_does_not_override_twelve_month_rule(self):
        self.assertFalse(profile_matches(job("12-month placement open to current postgraduate students and graduates.")))

    def test_current_module_domains_are_kept_by_domain_filter(self):
        for title, description in (("Graduate Nanomaterials Scientist", "Research nanomaterials and interfaces."),
                                   ("Graduate Optoelectronics Scientist", "Investigate optoelectronic devices.")):
            with self.subTest(title=title):
                self.assertTrue(profile_matches(job(description, title=title)))

    def test_degree_placements_remain_rejected_even_with_postgraduate_invitation(self):
        for text in ("Placement year; postgraduate students welcome.",
                     "Sandwich year; current Master's students may apply.",
                     "One-year placement as part of the degree; postgraduate students welcome.",
                     "Industrial placement year; graduates and students welcome."):
            with self.subTest(text=text):
                self.assertFalse(student_filter.student_matches(job(text)))

    def test_enrolment_preference_does_not_create_placement_requirement(self):
        self.assertTrue(profile_matches(job("Placement year eligibility preferred for this research internship.")))

    def test_graduation_cohorts_and_programme_start_are_independent(self):
        for text, expected in (("Graduating in 2027", True), ("2026-2028 graduates", True),
                               ("Programme starts October 2028", True), ("Class of 2028 only", False)):
            with self.subTest(text=text):
                self.assertEqual(graduation_filter.graduation_matches(job(text)), expected)

    def test_exact_and_named_month_start_boundaries(self):
        for value, expected in (("2027-09-30", False), ("2027-10-01", True),
                                ("30 September 2027", False), ("1 October 2027", True),
                                ("September 30, 2027", False), ("October 1, 2027", True)):
            with self.subTest(value=value):
                self.assertEqual(availability_filter.availability_matches(job("Start date: " + value)), expected)

    def test_application_and_posting_dates_do_not_become_start_dates(self):
        listing = job("Posted September 2026. Apply by September 2027. Materials research for 2027 graduates.")
        self.assertTrue(profile_matches(listing))
        self.assertEqual(availability_filter.assess_start(listing).status, "unknown")

    def test_flexible_preferred_start_kept_with_warning(self):
        for text in ("Start date: September 2027, flexible.", "Preferred start date: September 2027."):
            with self.subTest(text=text):
                listing = job(text)
                self.assertTrue(profile_matches(listing))
                self.assertTrue(listing.get("eligibility_warnings"))

    def test_start_date_field_is_checked(self):
        self.assertFalse(profile_matches(job(start_date="2027-09-01")))
        self.assertTrue(profile_matches(job(start_date="2027-10-01")))

    def test_start_date_on_next_line_is_checked_and_retained(self):
        for value, expected in (("September 2027", False), ("October 2027", True)):
            with self.subTest(value=value):
                listing = job("Start date:\n" + value)
                self.assertEqual(profile_matches(listing), expected)
                self.assertIn(value, select_job_evidence(listing["description"]))

    def test_warning_is_recomputed_after_description_enrichment(self):
        listing = job("Autumn 2027 start")
        self.assertTrue(profile_matches(listing))
        self.assertTrue(listing.get("eligibility_warnings"))
        listing["description"] = "October 2027 start"
        self.assertTrue(profile_matches(listing))
        self.assertFalse(listing.get("eligibility_warnings"))

    def test_msc_and_start_barriers_run_before_provider_and_detail_calls(self):
        listings = [job(text) for text in ("Master's required, immediate start before MSc completion",
                    "Must already hold a completed Master's degree", "September 2027 fixed start",
                    "Industrial placement year; must return to university afterwards", "2026 graduates only")]
        with patch.object(availability_filter, "date", wraps=date) as clock, \
             patch.object(job_scorer, "generate") as generate, \
             patch.object(job_scorer, "fetch_job_description") as fetch:
            clock.today.return_value = date(2026, 10, 29)
            results = job_scorer.score_jobs_batch(listings, persist=False)
        self.assertEqual(results, [{"score": 0}] * len(listings))
        generate.assert_not_called()
        fetch.assert_not_called()

    def test_ambiguous_start_warning_reaches_scoring_context_and_result(self):
        listing = job("Research batteries; Autumn 2027 start.")
        with patch.object(job_scorer, "distilled_profile", return_value="Current MSc student; not completed"), \
             patch.object(job_scorer, "generate", return_value='{"s":[78]}') as generate:
            result = job_scorer.score_job(listing, persist=False)
        self.assertEqual(result["score"], 78)
        self.assertTrue(result["eligibility_warnings"])
        self.assertIn("Needs confirmation:", generate.call_args.args[1])

    def test_start_date_and_completed_degree_evidence_survives_long_jd(self):
        text = "Responsibilities\n" + "\n".join(f"Analyse materials sample {i}." for i in range(100))
        text += "\nRequirements\nMust already hold a completed Master's degree.\nStart date: September 2027."
        evidence = select_job_evidence(text)
        self.assertIn("completed Master's degree", evidence)
        self.assertIn("Start date: September 2027", evidence)
        self.assertLess(evidence.index("Start date"), evidence.index("Analyse materials"))
        self.assertLessEqual(len(evidence), 2400)

    def test_profile_retains_two_education_states_and_all_modules_and_projects(self):
        profile = build_candidate_profile(MSC_CV, MSC_PROFILE)
        for text in ("Current MSc Advanced Materials Science and Engineering", "Imperial College London",
                     "2026-2027", "in_progress", "Highest completed education: bachelors", "2027-10-01",
                     "candidate graduation year: 2027", "First-Class Honours", *MODULES,
                     "Energy - 80%", "Electrochemistry and Interfaces - 79%",
                     "Molecules and Materials for the Modern World - 77%", *EXPERIENCES):
            with self.subTest(text=text):
                self.assertIn(text, profile)
        self.assertLessEqual(len(profile), PROFILE_CHAR_LIMIT)
        self.assertIn("Education: Imperial College London; MSc", profile)
        self.assertIn("Example UK University; BSc Chemistry", profile)
        self.assertNotIn("MSc completed", profile)

    def test_scoring_instructions_require_actual_fit_and_no_prestige_bonus(self):
        for text in ("not claim the MSc is already completed", "institutional prestige", "1 October 2027",
                     "energy conversion/storage", "nanomaterials", "optoelectronic", "materials sustainability"):
            self.assertIn(text, job_scorer.SCORE_SYSTEM)

    def test_api_profile_exposes_current_and_completed_states(self):
        from api import server
        with patch.object(server, "USER_PROFILE", MSC_PROFILE), \
             patch.object(server, "get_store_meta", return_value={}):
            state = server.meta()["profile"]
        for name in ("highest_completed_education", "current_education", "current_education_status",
                     "graduation_year", "available_from"):
            self.assertEqual(state[name], MSC_PROFILE[name])

    def test_saved_jobs_recompute_ambiguous_start_flags_without_schema_changes(self):
        with TemporaryDirectory() as directory, \
             patch.object(database, "DB_PATH", Path(directory) / "jobs.db"), \
             patch.object(database, "_schema_ready", False), \
             patch.object(job_store, "_meta_cache", None):
            job_store.upsert_jobs([job("Autumn 2027 start; battery research.", job_id="example_msc")])
            records = job_store.get_all_jobs()
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]["eligibility_warnings"])

    def test_default_query_list_retains_old_queries_and_adds_2027_queries(self):
        queries = config.DEFAULT_BROAD_SEARCH_QUERIES.split(",")
        self.assertEqual(len(queries), len(set(queries)))
        for query in (*YEAR_QUERIES, "graduate energy", "materials scientist", "electrochemistry"):
            self.assertIn(query, queries)

    def test_first_two_query_groups_prioritise_2027_energy_and_materials(self):
        queries = config.DEFAULT_BROAD_SEARCH_QUERIES.split(",")
        self.assertEqual(queries[:8], [
            "graduate energy", "2027 graduate energy", "energy graduate scheme 2027", "energy analyst",
            "materials graduate", "materials graduate 2027", "graduate materials scientist 2027", "electrochemistry",
        ])
        with patch.object(job_fetcher, "BROAD_SEARCH_QUERIES", queries), \
             patch.object(job_fetcher, "BROAD_SEARCH_QUERIES_PER_CYCLE", 4), \
             patch.object(job_fetcher, "ENABLE_BROAD_LINKEDIN_SEARCH", True):
            for offset in (0, 4):
                with patch.object(job_fetcher, "_broad_offset", offset):
                    plan = job_fetcher.linkedin_search_plan(["Example Energy"], [])
                self.assertEqual([q for kind, q in plan if kind == "broad"], queries[offset:offset + 4])

    def test_profile_reserves_headroom_even_with_excess_optional_research(self):
        extra = "".join(f"- Analysed energy measurement {i} for an electrochemistry research experiment.\n" for i in range(80))
        text = MSC_CV.replace("- Wrote a technical report.\n", "- Wrote a technical report.\n" + extra)
        profile = build_candidate_profile(text, MSC_PROFILE)
        self.assertEqual(PROFILE_CHAR_LIMIT, 4800)
        self.assertGreaterEqual(PROFILE_CHAR_LIMIT - len(profile), 300)
        self.assertEqual(PROFILE_HEADROOM_CHARS, 300)
        for fact in (*EXPERIENCES, *MODULES, "Energy - 80%", "Electrochemistry and Interfaces - 79%",
                     "2027-10-01", "in_progress", "Highest completed education: bachelors",
                     "0 years of full-time professional experience", "electrochemistry", "XRD"):
            self.assertIn(fact, profile)

    def test_leadership_and_languages_are_compact_in_scoring_only(self):
        profile = build_candidate_profile(MSC_CV, MSC_PROFILE)
        self.assertIn("Leadership (separate): Society Secretary", profile)
        self.assertIn("Languages (separate): English; Mandarin.", profile)
        self.assertNotIn("Organised student activities", profile)
        self.assertNotIn("Professional Working", profile)
        self.assertIn("Organised student activities", MSC_CV)
        self.assertIn("Professional Working", MSC_CV)

    def test_query_rotation_covers_all_queries_without_expanding_cycle(self):
        queries = config.DEFAULT_BROAD_SEARCH_QUERIES.split(",")
        covered = set()
        with patch.object(job_fetcher, "BROAD_SEARCH_QUERIES", queries), \
             patch.object(job_fetcher, "BROAD_SEARCH_QUERIES_PER_CYCLE", 4), \
             patch.object(job_fetcher, "ENABLE_BROAD_LINKEDIN_SEARCH", True):
            for offset in range(0, len(queries), 4):
                with patch.object(job_fetcher, "_broad_offset", offset):
                    plan = job_fetcher.linkedin_search_plan(["Example Energy"], [])
                broad = [query for kind, query in plan if kind == "broad"]
                self.assertEqual(len(broad), 4)
                covered.update(broad)
        self.assertEqual(covered, set(queries))


if __name__ == "__main__":
    unittest.main()
