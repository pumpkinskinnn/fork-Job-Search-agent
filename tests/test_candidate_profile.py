"""Synthetic, identifier-free fixtures; no private CV or provider is required."""

import unittest
from unittest.mock import patch

from ai.candidate_profile import PROFILE_CHAR_LIMIT, build_candidate_profile
from ai.job_scorer import distilled_profile
from ai.resume_builder import parse_master_resume
from ai.resume_sections import split_resume_sections
from config import DEFAULT_TARGET_ROLES


CANDIDATE = {
    "location": "London, United Kingdom",
    "experience_years": 0,
    "target_roles": DEFAULT_TARGET_ROLES.split(","),
}
EXPERIENCES = (
    "Summer Undergraduate Research Programme",
    "Research Internship",
    "Undergraduate Research Support Scheme",
)
MODULES = (
    "Energy - 80%", "Electrochemistry and Interfaces - 79%",
    "Molecules and Materials for the Modern World - 77%", "Data Science for Chemists - 76%",
    "Inorganic Materials from Complexes to Solids - 72%", "Chemistry for Sustainability - 62%",
    "Project Management - 69%",
)
CV = """CANDIDATE PROFILE
Recent BSc Chemistry graduate with First-Class Honours.
Based in London, UK.
Target areas:
Energy, sustainability, battery technology and materials science.

EDUCATION
Example UK University
BSc Chemistry, First-Class Honours
Relevant modules:
{modules}

SKILLS
Energy and Materials: electrochemistry, interfaces, functional materials
Characterisation: XRD, SEM, NMR, FTIR, UV-Vis, GPC/SEC
Laboratory: glovebox techniques, materials synthesis
Data and Software: Microsoft Excel, Origin, data analysis

PROJECT AND RESEARCH EXPERIENCE
Summer Undergraduate Research Programme
Example Overseas University
Jun - Aug
- Investigated surface chemistry and interfacial behaviour.
- Used 11 iterative synthesis trials to target approximately 1,400 nm particles.
- Wrote a technical report.

Research Internship
Example UK University
Apr - Jun
- Synthesised titanium(IV)-oxo clusters for photocatalysis research.
- Used X-ray diffraction and studied electron-transfer processes.

Undergraduate Research Support Scheme
Example UK University
Jun - Aug
- Studied sustainable polymer synthesis and electrochemically mediated RAFT.
- Analysed polymers using GPC/SEC.
- Presented research to technical and non-specialist audiences.

LEADERSHIP AND ACTIVITIES
Society Secretary
Example Society
- Organised student activities.

LANGUAGES
English - Professional Working
Mandarin - Native
""".format(modules="\n".join("- " + module for module in MODULES))


class CandidateProfileTests(unittest.TestCase):
    def test_all_three_research_entries_and_key_evidence_are_preserved(self):
        profile = build_candidate_profile(CV, CANDIDATE)
        for title in EXPERIENCES:
            with self.subTest(title=title):
                self.assertIn(title, profile)
        for evidence in (
            "11 iterative synthesis trials", "1,400 nm", "surface chemistry", "interfacial behaviour",
            "titanium(IV)-oxo", "photocatalysis", "electron-transfer", "sustainable polymer synthesis",
            "electrochemically mediated RAFT", "GPC/SEC", "technical and non-specialist audiences",
        ):
            with self.subTest(evidence=evidence):
                self.assertIn(evidence, profile)

    def test_complete_relevant_module_results(self):
        profile = build_candidate_profile(CV, CANDIDATE)
        for module in MODULES:
            with self.subTest(module=module):
                self.assertIn(module, profile)
        self.assertIn("Project Management - 69%.", profile)

    def test_skill_categories_and_complete_keywords(self):
        profile = build_candidate_profile(CV, CANDIDATE)
        for category in ("Energy and Materials", "Characterisation", "Laboratory", "Data and Software"):
            self.assertIn("Skills / " + category + ":", profile)
        for keyword in ("electrochemistry", "XRD", "SEM", "NMR", "FTIR", "UV-Vis", "GPC/SEC",
                        "glovebox", "materials synthesis", "Excel", "Origin", "data analysis"):
            self.assertIn(keyword, profile)
        self.assertIn("Microsoft Excel; Origin; data analysis.", profile)

    def test_all_configured_roles_and_target_areas_are_present(self):
        profile = build_candidate_profile(CV, CANDIDATE)
        for role in CANDIDATE["target_roles"]:
            with self.subTest(role=role):
                self.assertIn(role, profile)
        for area in ("sustainability", "battery technology", "materials science"):
            self.assertIn(area, profile)

    def test_research_and_internship_heading_variants(self):
        for heading in ("PROJECT AND RESEARCH EXPERIENCE", "RESEARCH EXPERIENCE", "PROJECT EXPERIENCE", "INTERNSHIPS"):
            with self.subTest(heading=heading):
                text = CV.replace("PROJECT AND RESEARCH EXPERIENCE", heading)
                parsed = parse_master_resume(text)
                self.assertEqual([entry["header"] for entry in parsed["experience"]], list(EXPERIENCES))
                self.assertIn("Example Overseas University", parsed["experience"][0]["subheader"])
                self.assertIn("Jun - Aug", parsed["experience"][0]["subheader"])

    def test_leadership_and_languages_are_separate_from_experience(self):
        for heading in ("LEADERSHIP AND ACTIVITIES", "LEADERSHIP", "ACTIVITIES"):
            with self.subTest(heading=heading):
                text = CV.replace("LEADERSHIP AND ACTIVITIES", heading)
                parsed = parse_master_resume(text)
                self.assertEqual([entry["header"] for entry in parsed["experience"]], list(EXPERIENCES))
                self.assertEqual(parsed["leadership"][0]["header"], "Society Secretary")
                self.assertEqual(parsed["languages"], ["English - Professional Working", "Mandarin - Native"])
                experience = "\n".join(split_resume_sections(text)["EXPERIENCE"])
                self.assertNotIn("Society Secretary", experience)
                self.assertNotIn("Mandarin", experience)

    def test_oversized_bullet_does_not_hide_later_projects_or_leave_a_fragment(self):
        oversized = "- OVERSIZED_MARKER " + "electrochemistry energy " * 1000 + "END_MARKER.\n"
        text = CV.replace("- Investigated surface", oversized + "- Investigated surface")
        profile = build_candidate_profile(text, CANDIDATE)
        self.assertLessEqual(len(profile), PROFILE_CHAR_LIMIT)
        self.assertNotIn("OVERSIZED_MARKER", profile)
        for title in EXPERIENCES:
            self.assertIn(title, profile)
        self.assertIn("11 iterative synthesis trials", profile)
        self.assertTrue(profile.endswith("."))
        # Every selected source bullet is still a whole, complete fact.
        for line in profile.splitlines():
            if line.startswith("- "):
                self.assertTrue(line.endswith((".", "!", "?")), line)

    def test_tight_budget_preserves_entry_coverage_and_complete_units(self):
        many_bullets = "".join(f"- Analysed energy measurement {i} in a complete research experiment.\n" for i in range(100))
        text = CV.replace("- Wrote a technical report.\n", "- Wrote a technical report.\n" + many_bullets)
        profile = build_candidate_profile(text, CANDIDATE, limit=2600)
        self.assertLessEqual(len(profile), 2600)
        for title in EXPERIENCES:
            self.assertIn(title, profile)
        self.assertTrue(profile.endswith("."))
        for line in profile.splitlines():
            self.assertTrue(line.endswith((".", ":", "!", "?")), line)

    def test_overlarge_mandatory_scope_fails_instead_of_being_truncated(self):
        candidate = dict(CANDIDATE, target_roles=["Very long complete role " * 1000])
        with self.assertRaisesRegex(ValueError, "Mandatory candidate"):
            build_candidate_profile(CV, candidate)

    def test_multiline_skill_categories(self):
        text = CV.replace("Characterisation: XRD, SEM, NMR, FTIR, UV-Vis, GPC/SEC",
                          "Characterisation:\nXRD, SEM, NMR, FTIR, UV-Vis, GPC/SEC")
        profile = build_candidate_profile(text, CANDIDATE)
        self.assertIn("Skills / Characterisation: XRD; SEM; NMR; FTIR; UV-Vis; GPC/SEC.", profile)

    def test_scorer_uses_structured_profile_without_provider_calls(self):
        with patch("ai.job_scorer.USER_PROFILE", CANDIDATE), \
             patch("ai.job_scorer.generate", side_effect=AssertionError("Provider call forbidden")) as generate:
            profile = distilled_profile(CV)
        self.assertEqual(profile, build_candidate_profile(CV, CANDIDATE))
        self.assertLessEqual(len(profile), PROFILE_CHAR_LIMIT)
        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
