import unittest

from tests.legacy_candidate import BscCandidateTestCase
from unittest.mock import patch

from config import DEFAULT_TARGET_ROLES
from jobs import contract_filter, education_filter, experience_filter, location_filter
from jobs.company_utils import role_matches
from jobs.profile_filter import profile_matches


def job(title="Energy Analyst", description="", location="London, United Kingdom"):
    return {"title": title, "description": description, "location": location}


class GraduateFiltersTests(BscCandidateTestCase):
    def setUp(self):
        super().setUp()
        for module, name, value in (
            (experience_filter, "FILTER_BY_EXPERIENCE", True),
            (experience_filter, "EXPERIENCE_MAX", 0),
            (education_filter, "FILTER_BY_EDUCATION", True),
            (education_filter, "MAX_EDUCATION", "bachelors"),
            (contract_filter, "REJECT_12_MONTH_CONTRACT", True),
            (location_filter, "FILTER_BY_LOCATION", True),
        ):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_requested_accept_examples(self):
        for title in (
            "Graduate Energy Analyst – no previous experience required",
            "Junior Sustainability Analyst",
            "Energy Analyst – experience desirable but not essential",
            "Graduate Materials Scientist – academic research experience welcomed",
            "Battery Research Scientist – MSc preferred, BSc accepted",
            "Energy Consultant – 0-1 years experience",
        ):
            with self.subTest(title=title):
                self.assertTrue(profile_matches(job(title)))

    def test_requested_reject_examples(self):
        for title in (
            "Senior Energy Analyst",
            "Energy Analyst – 2 years professional experience required",
            "Sustainability Consultant – previous consultancy experience required",
            "Research Scientist – PhD required",
            "Graduate Energy Analyst – 12-month fixed-term contract",
            "Energy Analyst – one-year FTC",
        ):
            with self.subTest(title=title):
                self.assertFalse(profile_matches(job(title)))

    def test_senior_titles_and_ordinary_engineer(self):
        for title in ("Senior", "Lead", "Principal", "Staff", "Manager", "Director", "Head of", "VP", "Chief", "Sr."):
            with self.subTest(title=title):
                self.assertFalse(experience_filter.experience_matches(job(title + " Energy Analyst")))
        for title in ("Research Engineer", "Graduate Materials Engineer", "New-graduate Scientist",
                      "Entry-level Energy Analyst", "Trainee Electrochemist", "Battery Internship"):
            with self.subTest(title=title):
                self.assertTrue(experience_filter.experience_matches(job(title)))

    def test_explicit_industry_requirements_without_numeric_years(self):
        for description in (
            "Previous experience in the energy industry is required",
            "Must have professional experience in electrochemistry",
            "Proven industry experience required",
            "Commercial experience required",
            "Previous consultancy experience is essential",
            "Requirements:\nPrevious industry experience",
        ):
            with self.subTest(description=description):
                self.assertFalse(experience_filter.experience_matches(job(description=description)))

    def test_preferences_and_negation(self):
        for qualifier in ("preferred", "desirable", "advantageous", "a plus", "beneficial",
                          "nice to have", "optional", "not required", "not essential"):
            with self.subTest(qualifier=qualifier):
                self.assertTrue(experience_filter.experience_matches(job(description=f"2 years of industry experience {qualifier}")))
        for description in ("No professional experience required", "Desirable:\nTwo years of consultancy experience",
                            "Requirements:\nIndustry experience desirable but not essential"):
            with self.subTest(description=description):
                self.assertTrue(experience_filter.experience_matches(job(description=description)))

    def test_numeric_years_and_zero_ranges(self):
        for description in ("At least 1 year of relevant professional experience", "2+ years industry experience",
                            "One year of commercial experience required", "Must have two years' professional experience",
                            "Experience: 1+ years in industry"):
            with self.subTest(description=description):
                self.assertFalse(experience_filter.experience_matches(job(description=description)))
        for description in ("0-1 years professional experience", "0–2 years of experience",
                            "0 to 1 years industry experience", "2 years of experience", "1 year university project"):
            with self.subTest(description=description):
                self.assertTrue(experience_filter.experience_matches(job(description=description)))
        self.assertEqual(experience_filter._extract_year_requirements("0-1 years experience"), (0, 1))

    def test_academic_alternatives(self):
        for description in (
            "2 years of academic research experience required",
            "Relevant experience required, including university research or internships",
            "1 year of professional or academic research experience required",
            "1 year relevant work experience required (internships count)",
            "1 year professional experience required, including academic research",
            "Experience from university placements welcomed",
        ):
            with self.subTest(description=description):
                self.assertTrue(experience_filter.experience_matches(job(description=description)))
        self.assertFalse(experience_filter.experience_matches(job(description=
            "Professional experience required. Academic projects desirable.")))

    def test_independent_preferences_do_not_hide_requirements(self):
        for description in (
            "Industry experience preferred; commercial experience required.",
            "Professional experience required. A chemistry degree is desirable.",
            "<ul><li>Industry experience required</li><li>PhD desirable</li></ul>",
            "Industry experience not required but previous commercial experience required",
            "Industry experience preferred and previous consultancy experience required",
        ):
            with self.subTest(description=description):
                self.assertFalse(experience_filter.experience_matches(job(description=description)))

    def test_bachelors_degree_ceiling(self):
        for description in ("Master's degree required", "MSc essential", "Ph.D. required", "DPhil required",
                            "Requirements:\nA master's in materials science", "BSc plus MSc required",
                            "BSc with MSc or PhD required", "No MSc required but PhD required",
                            "Postgraduate degree required"):
            with self.subTest(description=description):
                self.assertFalse(education_filter.education_matches(job(description=description)))
        for description in ("STEM degree required", "Chemistry degree required", "Science degree required",
                            "Degree in materials/chemistry/engineering or a related discipline",
                            "BSc required, MSc desirable", "PhD preferred", "MSc advantageous",
                            "BSc or MSc required", "MSc or BSc required", "BSc/MSc in chemistry required",
                            "BSc required and MSc preferred", "No MSc required", "No PhD is required",
                            "Requirements:\nBSc required\nPhD desirable"):
            with self.subTest(description=description):
                self.assertTrue(education_filter.education_matches(job(description=description)))

    def test_education_independent_requirements_and_configuration(self):
        self.assertFalse(education_filter.education_matches(job(description="BSc required. PhD required.")))
        self.assertFalse(education_filter.education_matches(job(description="MSc preferred; PhD required.")))
        with patch.object(education_filter, "MAX_EDUCATION", "masters"):
            self.assertTrue(education_filter.education_matches(job(description="MSc required")))
            self.assertFalse(education_filter.education_matches(job(description="PhD required")))
            self.assertTrue(education_filter.education_matches(job(description="MSc or PhD required")))
        with patch.object(education_filter, "MAX_EDUCATION", "phd"):
            self.assertTrue(education_filter.education_matches(job(description="PhD required")))

    def test_contract_variants(self):
        for description in ("12 month contract", "12-month contract", "12 months fixed term", "12-month FTC",
                            "fixed-term contract for 12 months", "one-year fixed-term contract", "one-year FTC",
                            "temporary contract for twelve months", "12 month temporary role",
                            "FTC: 12 months", "contract length: 12 months", "12‑month fixed‑term contract"):
            with self.subTest(description=description):
                self.assertFalse(contract_filter.contract_matches(job(description=description)))

    def test_unrelated_durations_and_other_contracts(self):
        for description in ("12 months training provided", "12 months research experience preferred",
                            "Permanent contract, with 12 months training provided", "6-month fixed-term contract",
                            "24 month contract", "One-year training programme", "Permanent position after 12 months training"):
            with self.subTest(description=description):
                self.assertTrue(contract_filter.contract_matches(job(description=description)))

    def test_html_qualifications(self):
        self.assertFalse(profile_matches(job(description="<p><strong>PhD</strong> required</p>")))
        self.assertTrue(profile_matches(job(description="<p><strong>MSc</strong> preferred, BSc accepted</p>")))
        self.assertFalse(profile_matches(job(description="<p>12-month <b>fixed-term</b> contract</p>")))

    def test_configuration_switches(self):
        with patch.object(contract_filter, "REJECT_12_MONTH_CONTRACT", False):
            self.assertTrue(profile_matches(job(description="12-month FTC")))
        with patch.object(experience_filter, "FILTER_BY_EXPERIENCE", False):
            self.assertTrue(experience_filter.experience_matches(job("Senior Energy Analyst")))
        with patch.object(education_filter, "FILTER_BY_EDUCATION", False):
            self.assertTrue(education_filter.education_matches(job(description="PhD required")))

    def test_uk_and_overseas_locations(self):
        for location in ("London", "London, UK (Hybrid)", "Greater London", "Reading, United Kingdom", "UK Remote", "Remote - United Kingdom", "Northern Ireland", ""):
            with self.subTest(location=location):
                self.assertTrue(location_filter.location_matches(job(location=location)))
        for location in ("London, Ontario", "London, Canada", "New London, Connecticut", "Paris, France", "Berlin", "Remote - US", "Remote", "Worldwide"):
            with self.subTest(location=location):
                self.assertFalse(location_filter.location_matches(job(location=location)))
        self.assertTrue(location_filter.location_matches(job(location="Remote", description="Remote role for UK-based candidates.")))

    def test_related_scientific_roles_are_not_accidentally_excluded(self):
        roles = DEFAULT_TARGET_ROLES.split(",")
        for title in roles + ["Graduate Process Engineer", "Laboratory Technician", "Research Assistant", "Junior STEM Consultant", "Electrochemical Researcher"]:
            with self.subTest(title=title):
                self.assertTrue(role_matches(title, roles))
        for title in ("Sales Representative", "Software Developer", "Investment Banker"):
            with self.subTest(title=title):
                self.assertFalse(role_matches(title, roles))


if __name__ == "__main__":
    unittest.main()
