import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pypdf import PdfReader

from ai import ats_optimizer, job_scorer, resume_builder
from ai.cover_letter import _contact_line_for_job


CV = """Sample Graduate
sample@example.com | London, United Kingdom
SUMMARY
Recent chemistry graduate seeking energy and materials research roles.
EDUCATION
BSc Chemistry, First-Class Honours
{heading}
University Research Project — Battery Materials
- Analysed electrochemical measurements in a university research project
SKILLS
Laboratory: electrochemistry, materials characterisation
Analysis: spreadsheets, data analysis
PROJECTS
University Sustainability Project
- Analysed renewable energy data
"""


class ScoringAndCvTests(unittest.TestCase):
    def test_research_headings_preserve_research_and_education(self):
        for heading in ("PROJECT & RESEARCH EXPERIENCE", "RESEARCH EXPERIENCE", "Project and Research Experience:",
                        "RESEARCH & PROJECT EXPERIENCE", "PROJECT EXPERIENCE", "INTERNSHIP EXPERIENCE", "EXPERIENCE"):
            with self.subTest(heading=heading):
                cv = CV.format(heading=heading)
                profile = job_scorer.distilled_profile(cv)
                self.assertIn("Analysed electrochemical measurements", profile)
                self.assertIn("First-Class Honours", profile)
                self.assertIn("University Sustainability Project", profile)
                self.assertNotIn("SKILLS", job_scorer._section(cv, "EXPERIENCE"))
                parsed = resume_builder.parse_master_resume(cv)
                self.assertEqual(len(parsed["experience"]), 1)
                self.assertIn("university research project", parsed["experience"][0]["bullets"][0])
                self.assertIn("First-Class Honours", " ".join(parsed["education"]))

    def test_score_rejects_full_description_mismatch_before_model(self):
        jobs = [
            {"title": "Energy Analyst", "location": "London, UK",
             "description": "Renewable energy analysis. " * 100 + "Two years professional experience required."},
            {"title": "Graduate Materials Scientist", "location": "London, UK",
             "description": "Academic research welcomed. Industry experience desirable."},
        ]
        with patch.object(job_scorer, "distilled_profile", return_value="First-Class BSc Chemistry; zero industry experience"), \
             patch.object(job_scorer, "generate", return_value='{"s":[85]}') as generate:
            results = job_scorer.score_jobs_batch(jobs, persist=False)
        self.assertEqual([r["score"] for r in results], [0, 85])
        self.assertNotIn("Two years professional experience required", generate.call_args.args[1])
        system = generate.call_args.args[0]
        for text in ("suitability 25%", "relevance 25%", "fit 25%", "skills 15%", "fit 10%", "Do not invent", "London", "permanent graduate"):
            self.assertIn(text, system)

    def test_hard_rejection_is_persisted_without_model_call(self):
        listing = {"job_id": "test_1", "title": "Energy Analyst", "description": "Commercial experience required"}
        with patch.object(job_scorer, "distilled_profile", return_value="graduate"), \
             patch.object(job_scorer, "generate") as generate, \
             patch("jobs.job_store.save_job_score") as save:
            result = job_scorer.score_job(listing)
        self.assertEqual(result["score"], 0)
        self.assertEqual(save.call_args.args[1]["score"], 0)
        generate.assert_not_called()

    def test_other_hard_filters_and_missing_jd_limit_scores(self):
        listings = [
            {"title": "Senior Energy Analyst", "description": "Renewable energy analysis", "location": "London"},
            {"title": "Research Scientist", "description": "PhD required", "location": "London"},
            {"title": "Graduate Analyst", "description": "12-month FTC", "location": "London"},
            {"title": "Graduate Scientist", "description": "Graduate role", "location": "Paris"},
            {"title": "Graduate Energy Analyst", "location": "London"},
        ]
        with patch.object(job_scorer, "distilled_profile", return_value="graduate"), \
             patch.object(job_scorer, "generate", return_value='{"s":[95]}'):
            results = job_scorer.score_jobs_batch(listings, persist=False)
        self.assertEqual([result["score"] for result in results], [0, 0, 0, 0, 60])

    def test_invalid_batch_length_is_not_accepted(self):
        with self.assertRaises(ValueError):
            job_scorer._parse_scores('{"s":[90]}', 2)

    def test_tailoring_does_not_add_skills_or_years(self):
        groups = [{"name": "Analysis", "items": ["data analysis", "spreadsheets"]}]
        original = copy.deepcopy(groups)
        with patch.object(ats_optimizer, "extract_jd_terms", return_value=(["electrochemistry", "data analysis"], ["Python"])):
            prepared = ats_optimizer.prepare_skills(groups, "Python and electrochemistry required")
        self.assertEqual(groups, original)
        self.assertEqual(prepared["groups"], original)
        self.assertEqual(prepared["added_skills"], [])
        self.assertNotIn("Python", " ".join(prepared["skill_lines"]))
        summary = "Graduate with 0 years of professional industry experience."
        self.assertEqual(ats_optimizer.align_summary_years(summary, "5 years professional experience required"), summary)
        self.assertNotIn("summary must say", resume_builder.RESUME_PROMPT)
        self.assertIn("Never increase", resume_builder.RESUME_PROMPT)

    def test_cover_letter_does_not_append_india(self):
        contact = "sample@example.com | London, United Kingdom"
        self.assertEqual(_contact_line_for_job(contact, {"location": "London, UK"}), contact)

    def test_research_cv_renders_to_pdf(self):
        data = resume_builder.parse_master_resume(CV.format(heading="RESEARCH EXPERIENCE"))
        data["skills"] = ["Electrochemistry, data analysis"]
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "research-cv.pdf"
            resume_builder.write_resume_pdf(data, path)
            reader = PdfReader(path)
            self.assertEqual(len(reader.pages), 1)
            text = reader.pages[0].extract_text()
            self.assertIn("Analysed electrochemical measurements", text)
            self.assertIn("First-Class Honours", text)


if __name__ == "__main__":
    unittest.main()
