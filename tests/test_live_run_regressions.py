"""Offline regressions for the first live dry run's parsing/eligibility failures."""

import json
import re
import unittest
from unittest.mock import Mock, patch

from ai import job_scorer
from ai.job_evidence import EvidenceBudgetError, JOB_EVIDENCE_CHAR_LIMIT, select_job_evidence
from jobs import education_filter, experience_filter, graduation_filter
from jobs.ats.lever import fetch_lever_jobs, normalize_lever_description
from jobs.profile_filter import pre_description_matches, profile_matches


def job(description, **fields):
    return {"title": "Graduate Energy Analyst", "company": "Example Energy",
            "location": "London, United Kingdom", "description": description, **fields}


def lever_payload(**fields):
    return {
        "id": "example", "text": "Graduate Battery Scientist", "createdAt": 1791244800000,
        "hostedUrl": "https://jobs.lever.co/example/example",
        "categories": {"location": "London, United Kingdom", "commitment": "Permanent"},
        "description": "<p>Research battery materials and clean energy.</p>",
        "descriptionPlain": "Research battery materials and clean energy.",
        "lists": [
            {"text": "Responsibilities", "content": "<ul><li>Analyse electrochemical measurements.</li></ul>"},
            {"text": "Requirements", "content": (
                "<ul><li>Bachelor's degree in Chemistry, Materials or related discipline required.</li>"
                "<li>0-2 years of work experience.</li><li>Experience with XRD required.</li></ul>"
            )},
            {"text": "Preferred", "content": "<ul><li>Master's degree desirable.</li></ul>"},
        ],
        "additional": "<p>Programme starts September 2027.</p>",
        **fields,
    }


class EligibilityRegressionTests(unittest.TestCase):
    def setUp(self):
        for module, name, value in (
            (experience_filter, "FILTER_BY_EXPERIENCE", True),
            (experience_filter, "EXPERIENCE_MAX", 0),
            (education_filter, "FILTER_BY_EDUCATION", True),
            (education_filter, "MAX_EDUCATION", "bachelors"),
            (education_filter, "USER_PROFILE", {"education": "BSc Chemistry"}),
            (graduation_filter, "CANDIDATE_GRADUATION_YEAR", 2026),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_rystad_upper_bound_is_a_maximum(self):
        text = "Bachelor's or Master's degree. No more than three years of work experience."
        self.assertEqual(experience_filter._extract_year_requirements(text), (0, 3))
        self.assertTrue(profile_matches(job(text)))

    def test_other_upper_bounds_and_zero_ranges_keep_fresh_graduates(self):
        for text, bounds in (
            ("up to two years of experience", (0, 2)),
            ("up to 2 years of professional experience required", (0, 2)),
            ("0-2 years experience", (0, 2)),
            ("no more than 3 years of industry experience", (0, 3)),
            ("at most two years of work experience", (0, 2)),
        ):
            with self.subTest(text=text):
                self.assertEqual(experience_filter._extract_year_requirements(text), bounds)
                self.assertTrue(experience_filter.experience_matches(job(text)))

    def test_wsp_programme_duration_is_not_prior_experience(self):
        text = (
            "Our two-year Graduate Development Programme is designed to help you build "
            "the skills, experience and professional network needed to thrive at the start "
            "of your career with us."
        )
        self.assertEqual(experience_filter._extract_year_requirements(text), (None, None))
        self.assertTrue(profile_matches(job(text, title="Graduate Environmental Consultant")))

    def test_requested_programme_duration_examples(self):
        for text in (
            "graduate programme", "two-year graduate development programme",
            "two-year training programme", "programme lasting two years",
            "The graduate programme lasts two years and builds professional experience.",
            "Two-year training programme to develop the work experience needed in energy.",
        ):
            with self.subTest(text=text):
                self.assertEqual(experience_filter._extract_year_requirements(text), (None, None))
                self.assertTrue(experience_filter.experience_matches(job(text)))

    def test_programme_does_not_hide_independent_experience_requirement(self):
        for text in (
            "Two-year training programme. Three years industry experience required.",
            "Two-year training programme requires three years of professional experience.",
            "Two-year training programme with industry experience required.",
        ):
            with self.subTest(text=text):
                self.assertFalse(experience_filter.experience_matches(job(text)))

    def test_upper_bound_does_not_hide_a_separate_minimum(self):
        text = "Up to three years experience. At least one year of industry experience required."
        self.assertEqual(experience_filter._extract_year_requirements(text), (1, 3))
        self.assertFalse(experience_filter.experience_matches(job(text)))

    def test_masters_required_rejected(self):
        for text in ("Master's degree required", "Requirements\nA master's in materials science",
                     "A master's level qualification in Mechanical Engineering or Physics"):
            with self.subTest(text=text):
                self.assertFalse(profile_matches(job(text)))

    def test_masters_preferred_kept(self):
        for text in ("Master's preferred", "Master's degree desirable", "MSc advantageous",
                     "Preferred qualifications\nMaster's degree", "Desirable skills: MSc in Chemistry"):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_bachelors_or_masters_alternative_kept(self):
        for text in ("Bachelor's or Master's accepted", "MSc or BSc required", "BSc/MSc in Chemistry required"):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_phd_without_lower_alternative_rejected(self):
        self.assertFalse(profile_matches(job("PhD required in materials science")))
        self.assertTrue(profile_matches(job("Bachelor's or PhD in Chemistry required")))

    def test_incompatible_required_degree_families_rejected(self):
        for family in ("Electrical", "Power", "Mechanical", "Civil"):
            with self.subTest(family=family):
                self.assertFalse(profile_matches(job(f"Bachelor's degree in {family} Engineering required")))
                self.assertFalse(profile_matches(job(f"Requirements\nDegree in {family} Engineering")))

    def test_broad_scientific_alternatives_kept(self):
        for text in (
            "STEM degree required", "Science degree required", "Relevant scientific discipline required",
            "Bachelor's in electrical engineering or related discipline required",
            "Degree in engineering, chemistry, materials, science or related discipline required",
            "Chemistry/Materials/Engineering or related discipline degree required",
        ):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_optional_degree_discipline_and_narrative_kept(self):
        self.assertTrue(profile_matches(job("Electrical Engineering degree preferred")))
        self.assertTrue(profile_matches(job("Our team includes electrical engineering degree holders.")))
        self.assertTrue(profile_matches(job("Engineering skills required for battery testing.")))

    def test_unrelated_preferred_science_does_not_hide_required_engineering(self):
        for text in ("Electrical Engineering degree required. Chemistry knowledge preferred.",
                     "Bachelor's degree in Electrical Engineering required with Chemistry knowledge.",
                     "Electrical Engineering degree required and experience in materials science."):
            with self.subTest(text=text):
                self.assertFalse(profile_matches(job(text)))

    def test_lower_degree_alternative_does_not_hide_a_separate_phd_requirement(self):
        self.assertFalse(profile_matches(job("BSc or MSc and PhD required")))
        self.assertTrue(profile_matches(job("BSc or MSc or PhD required")))

    def test_required_graduation_cohort_rejected(self):
        for text in ("Applicants graduating in 2027", "2027 graduates only", "Graduation year: 2027"):
            with self.subTest(text=text):
                self.assertFalse(graduation_filter.graduation_matches(job(text)))
                self.assertFalse(profile_matches(job(text)))
                self.assertFalse(pre_description_matches(job(text)))

    def test_programme_start_year_is_not_graduation_year(self):
        for text in ("Programme starts September 2027", "2027 graduate programme starts in September",
                     "Graduate development programme 2027", "Graduate 2027 programme",
                     "Applicants graduating in 2026; starts September 2027"):
            with self.subTest(text=text):
                self.assertTrue(profile_matches(job(text)))

    def test_graduation_year_alternatives_ranges_and_configuration(self):
        for text in ("2026 or 2027 graduates only", "Applicants graduating in 2025-2027",
                     "Applicants graduating in 2026", "2027 graduates preferred"):
            with self.subTest(text=text):
                self.assertTrue(graduation_filter.graduation_matches(job(text)))
        with patch.object(graduation_filter, "CANDIDATE_GRADUATION_YEAR", 2027):
            self.assertTrue(graduation_filter.graduation_matches(job("Applicants graduating in 2027")))
            self.assertFalse(graduation_filter.graduation_matches(job("2026 graduates only")))

    def test_candidate_profile_contains_graduation_year(self):
        self.assertIn("candidate graduation year: 2026", job_scorer.distilled_profile("EDUCATION\nBSc Chemistry"))

    def test_inline_requirements_heading_is_enforced(self):
        self.assertFalse(profile_matches(job("Qualifications: Master's degree in Chemistry")))
        self.assertFalse(profile_matches(job("Requirements: Electrical Engineering degree")))
        self.assertTrue(profile_matches(job("Preferred qualifications: Master's degree in Chemistry")))


class LeverDescriptionRegressionTests(unittest.TestCase):
    def test_official_description_and_all_list_sections_retained(self):
        description = normalize_lever_description(lever_payload())
        for text in ("Research battery materials", "Responsibilities\nAnalyse electrochemical",
                     "Requirements\nBachelor's degree", "0-2 years of work experience",
                     "Experience with XRD required", "Preferred\nMaster's degree desirable",
                     "Additional information\nProgramme starts September 2027", "Contract type: Permanent"):
            self.assertIn(text, description)
        self.assertNotIn("<li>", description)
        self.assertEqual(description.count("Research battery materials"), 1)
        self.assertTrue(profile_matches(job(description)))

    def test_plain_fallbacks_and_explicit_requirements_retained(self):
        item = lever_payload(description="", additional="", additionalPlain="12-month fixed-term contract.",
                             requirements=["PhD required.", "Three years industry experience required."])
        description = normalize_lever_description(item)
        self.assertIn("Research battery materials", description)
        self.assertIn("Requirements\nPhD required.\nThree years industry experience required.", description)
        self.assertIn("Additional information\n12-month fixed-term contract.", description)
        self.assertFalse(profile_matches(job(description)))

    def test_adapter_uses_normalization_and_filters_list_requirements(self):
        for requirement in ("Master's degree required", "Bachelor's in Electrical Engineering required",
                            "2-5 years in a numerate commercial role", "12-month fixed-term contract",
                            "Applicants graduating in 2027"):
            with self.subTest(requirement=requirement):
                item = lever_payload(lists=[{"text": "Requirements", "content": f"<ul><li>{requirement}</li></ul>"}])
                response = Mock()
                response.json.return_value = [item]
                with patch("jobs.ats.lever.requests.get", return_value=response) as get:
                    listings = fetch_lever_jobs("Example Energy", "example")
                self.assertEqual(get.call_count, 1)
                self.assertEqual(len(listings), 1)
                self.assertIn(requirement, listings[0]["description"])
                self.assertFalse(profile_matches(listings[0]))


class ScoringEvidenceRegressionTests(unittest.TestCase):
    def test_late_eligibility_has_priority_over_long_introduction(self):
        description = "We research clean energy for customers. " * 150 + "\n" + normalize_lever_description(lever_payload())
        excerpt = select_job_evidence(description)
        self.assertLessEqual(len(excerpt), JOB_EVIDENCE_CHAR_LIMIT)
        for text in ("Bachelor's degree in Chemistry", "0-2 years of work experience",
                     "Experience with XRD required", "Contract: Permanent", "Master's degree desirable",
                     "Programme starts September 2027", "Analyse electrochemical measurements"):
            self.assertIn(text, excerpt)
        self.assertLess(excerpt.index("Bachelor's degree"), excerpt.index("Analyse electrochemical"))

    def test_complete_facts_not_prefixes_or_mid_sentence_fragments(self):
        facts = [f"Analyse battery measurement dataset {index} and report all findings to the research team." for index in range(20)]
        excerpt = select_job_evidence("Responsibilities\n" + "\n".join(facts), limit=250)
        self.assertLessEqual(len(excerpt), 250)
        self.assertTrue(excerpt)
        for line in excerpt.splitlines():
            self.assertIn(line.removeprefix("Responsibilities: "), facts)

    def test_preferences_do_not_receive_required_labels(self):
        excerpt = select_job_evidence("Requirements\nMaster's degree preferred.\nPreferred\nBSc Chemistry required.")
        self.assertIn("Preferred: Master's degree preferred.", excerpt)
        self.assertIn("Qualifications: BSc Chemistry required.", excerpt)
        self.assertNotIn("Required: Master's degree", excerpt)

    def test_inline_degree_formatting_retains_whole_requirement(self):
        excerpt = select_job_evidence("<h3>Requirements</h3><ul><li><b>Ph.D.</b> in Chemistry required.</li></ul>")
        self.assertIn("Ph.D. in Chemistry required.", excerpt)
        self.assertIn("Qualifications: M.Sc. required.", select_job_evidence("M.Sc. required."))

    def test_oversized_eligibility_fails_before_any_model_call(self):
        listing = job("Requirements\nBachelor's degree in Chemistry with " + "demonstrated laboratory knowledge " * 120 + "required.")
        with patch.object(job_scorer, "distilled_profile", return_value="graduate"), \
             patch.object(job_scorer, "generate") as generate:
            with self.assertRaises(EvidenceBudgetError):
                job_scorer.score_jobs_batch([listing, job("Battery research.")], persist=False)
        generate.assert_not_called()

    def test_late_hard_mismatches_are_capped_at_ten(self):
        requirements = ["Master's degree required", "PhD required", "Electrical Engineering degree required",
                        "Two years of professional experience required", "Applicants graduating in 2027"]
        listings = [job("Support clean energy research. " * 120 + "\nRequirements\n" + text) for text in requirements]
        with patch.object(job_scorer, "distilled_profile", return_value="BSc Chemistry; graduation year: 2026"), \
             patch.object(job_scorer, "generate", return_value=json.dumps({"s": [99] * len(listings)})) as generate:
            results = job_scorer.score_jobs_batch(listings, persist=False)
        self.assertEqual([result["score"] for result in results], [10] * len(listings))
        for requirement in requirements:
            self.assertIn(requirement, generate.call_args.args[1])
        self.assertIn("Deterministic eligibility mismatch: maximum score 10", generate.call_args.args[1])

    def test_eligible_regressions_are_not_capped(self):
        listings = [job(text) for text in ("No more than three years of work experience",
                    "Two-year graduate development programme", "Master's preferred", "STEM degree required",
                    "Programme starts September 2027")]
        with patch.object(job_scorer, "distilled_profile", return_value="graduate"), \
             patch.object(job_scorer, "generate", return_value=json.dumps({"s": [85] * len(listings)})):
            results = job_scorer.score_jobs_batch(listings, persist=False)
        self.assertEqual([result["score"] for result in results], [85] * len(listings))

    def test_total_prompt_is_bounded_without_losing_late_qualifications(self):
        description = "Responsibilities\n" + "\n".join(
            f"Analyse battery research dataset {index} and report detailed findings for our renewable energy project."
            for index in range(40)
        ) + "\nRequirements\nBachelor's degree in Chemistry required.\n0-2 years of work experience."
        listings = [job(description, company=f"Company {index}") for index in range(35)]

        def fake_generate(system, prompt, **kwargs):
            count = int(re.search(r"exactly (\d+) integers", prompt).group(1))
            self.assertLessEqual(len(system) + len(prompt), job_scorer._SCORE_PROMPT_CHARS)
            self.assertEqual(prompt.count("Bachelor's degree in Chemistry required"), count)
            self.assertEqual(prompt.count("0-2 years of work experience"), count)
            return json.dumps({"s": [85] * count})

        with patch.object(job_scorer, "distilled_profile", return_value="graduate"), \
             patch.object(job_scorer, "generate", side_effect=fake_generate) as generate:
            results = job_scorer.score_jobs_batch(listings, persist=False)
        self.assertGreater(generate.call_count, 1)
        self.assertEqual([result["score"] for result in results], [85] * len(listings))
