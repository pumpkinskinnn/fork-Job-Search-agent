import unittest

from tests.legacy_candidate import BscCandidateTestCase
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from jobs import contract_filter, database, education_filter, experience_filter, job_fetcher, job_store, location_filter
from jobs.ats import smartrecruiters, workday


class PipelineTests(BscCandidateTestCase):
    def setUp(self):
        super().setUp()
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        for module, name, value in (
            (database, "DB_PATH", Path(self.temp.name) / "jobs.db"),
            (database, "_schema_ready", False),
            (job_store, "_meta_cache", None),
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

    def test_stored_jobs_display_and_email_share_all_filters(self):
        listings = [
            {"job_id": "eligible", "title": "Graduate Energy Analyst", "company": "Example", "location": "London, UK"},
            {"job_id": "contract", "title": "Energy Analyst - one-year FTC", "company": "Example", "location": "London, UK"},
            {"job_id": "foreign", "title": "Energy Analyst", "company": "Example", "location": "Paris, France"},
            {"job_id": "senior", "title": "Senior Energy Analyst", "company": "Example", "location": "London, UK"},
            {"job_id": "phd", "title": "Research Scientist", "description": "PhD required", "company": "Example", "location": "London, UK"},
            {"job_id": "industry", "title": "Energy Consultant", "description": "Industry experience required", "company": "Example", "location": "London, UK"},
        ]
        job_store.upsert_jobs(listings)
        for listing in listings:
            job_store.save_job_score(listing["job_id"], {"score": 95})
        self.assertEqual([j["job_id"] for j in job_store.get_all_jobs()], ["eligible"])
        self.assertEqual([j["job_id"] for j in job_store.get_unnotified_high_score_jobs(70)], ["eligible"])
        # Keep previously applied jobs as history, but never email them again.
        job_store.set_job_applied("senior", True)
        self.assertEqual(job_store.purge_mismatched_jobs(), 4)
        self.assertIsNotNone(job_store.get_job("senior"))
        self.assertEqual([j["job_id"] for j in job_store.get_all_jobs(applied=True)], ["senior"])

    def test_contract_filter_still_works_when_other_filters_disabled(self):
        job_store.upsert_jobs([{"job_id": "contract", "title": "Graduate Scientist - 12-month FTC", "company": "Example", "location": "London"}])
        with patch.object(experience_filter, "FILTER_BY_EXPERIENCE", False), \
             patch.object(education_filter, "FILTER_BY_EDUCATION", False):
            self.assertEqual(job_store.get_all_jobs(), [])
            self.assertEqual(job_store.purge_mismatched_jobs(), 1)

    def test_cached_or_rate_limited_linkedin_jobs_still_get_title_filters(self):
        profile = {"filter_by_role": False}
        for cached, limited in ((True, False), (False, True)):
            with self.subTest(cached=cached, limited=limited), \
                 patch.object(job_fetcher, "USER_PROFILE", profile), \
                 patch.object(job_fetcher, "_known_job_ids", {"li_1"} if cached else set()), \
                 patch.object(job_fetcher, "linkedin_is_limited", return_value=limited), \
                 patch.object(job_fetcher, "attach_description") as attach:
                self.assertFalse(job_fetcher._is_relevant(
                    {"job_id": "li_1", "title": "Senior Energy Analyst", "location": "London"}, "", []))
                attach.assert_not_called()

    def test_linkedin_role_search_filters_stored_results(self):
        result = {"job_id": "li_1", "title": "Energy Analyst - 12-month FTC", "location": "London"}
        with patch.object(job_fetcher, "_known_job_ids", {"li_1"}), \
             patch.object(job_fetcher, "_fetch_search", return_value=[result]):
            self.assertEqual(job_fetcher.fetch_jobs_for_role("Energy Analyst", "London, United Kingdom", "r604800"), [])

    def test_career_fetch_pipeline_rejects_bad_profiles(self):
        from jobs import career_fetcher
        listings = [
            {"title": "Graduate Materials Scientist", "location": "London", "description": "Academic research welcomed"},
            {"title": "Graduate Materials Scientist", "location": "London", "description": "PhD required"},
            {"title": "Graduate Materials Scientist", "location": "London", "description": "12-month contract"},
            {"title": "Graduate Materials Scientist", "location": "Paris"},
        ]
        profile = {"filter_by_role": True, "target_roles": ["Materials Scientist"]}
        with patch.object(career_fetcher, "USER_PROFILE", profile), \
             patch.object(career_fetcher, "get_career_config", return_value={"ats": "greenhouse", "slug": "example"}), \
             patch.object(career_fetcher, "_fetch_from_ats", return_value=listings):
            self.assertEqual(career_fetcher.fetch_career_jobs_for_company("Example"), listings[:1])

    def test_empty_company_list_does_not_fetch_legacy_software_registry(self):
        from jobs import career_fetcher
        with patch.object(career_fetcher, "USER_PROFILE", {"target_companies": []}), \
             patch.object(career_fetcher, "fetch_career_jobs_for_company") as fetch:
            self.assertEqual(career_fetcher.fetch_all_career_jobs(), [])
        fetch.assert_not_called()

    def test_smartrecruiters_accepts_city_plus_country_not_literal_search_string(self):
        response = Mock()
        response.json.return_value = {"totalFound": 2, "content": [
            {"id": "1", "name": "Graduate Energy Analyst", "location": {"city": "London", "country": "gb"}},
            {"id": "2", "name": "Graduate Energy Analyst", "location": {"city": "Paris", "country": "fr"}},
        ]}
        with patch.object(smartrecruiters.requests, "get", return_value=response) as get:
            results = smartrecruiters.fetch_smartrecruiters_jobs("Example", "example", "London, United Kingdom")
        self.assertEqual([j["job_id"] for j in results], ["sr_example_1"])
        self.assertEqual(get.call_count, 1)

    def test_workday_uses_graduate_search_and_existing_page_budget(self):
        response = Mock()
        response.json.return_value = {"total": 1, "jobPostings": [
            {"title": "Graduate Energy Analyst", "locationsText": "London, UK", "externalPath": "/job/1"}
        ]}
        session = Mock()
        session.post.return_value = response
        with patch.object(workday, "get_session", return_value=session), \
             patch.object(workday, "WORKDAY_SEARCH_TERMS", ["graduate"]), \
             patch.object(workday, "_search_offsets", {}):
            results = workday.fetch_workday_jobs("Example", "example.wd5.myworkdayjobs.com/Careers")
        self.assertEqual(len(results), 1)
        self.assertEqual(session.post.call_args.kwargs["json"]["searchText"], "graduate")
        self.assertEqual(session.post.call_args.kwargs["json"]["limit"], 20)
        self.assertEqual(workday.MAX_JOBS, 400)

    def test_fastapi_startup_filters_then_displays_and_updates_graduate_job(self):
        from fastapi.testclient import TestClient
        from api import server
        job_store.upsert_jobs([
            {"job_id": "graduate", "title": "Graduate Energy Analyst", "company": "Example", "location": "London, UK"},
            {"job_id": "contract", "title": "Graduate Energy Analyst - 12-month FTC", "company": "Example", "location": "London, UK"},
        ])
        with patch.object(server, "start_background_polling"), \
             patch.object(server, "stop_background_polling"), \
             patch.object(server, "start_background_scoring"), \
             patch.object(server, "migrate_json_if_needed"), \
             patch.object(server, "get_email_config_issue", return_value="Email disabled in tests"), \
             patch.object(server, "send_test_email") as send, \
             TestClient(server.app) as client:
            response = client.get('/api/jobs')
            self.assertEqual(response.status_code, 200)
            self.assertEqual([j['job_id'] for j in response.json()['jobs']], ['graduate'])
            self.assertEqual(response.json()['jobs'][0]['description_status'], 'unavailable')
            self.assertEqual(response.json()['total'], 1)
            response = client.post('/api/jobs/graduate/applied', json={'applied': True})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['job']['is_applied'])
            self.assertEqual(client.get('/api/jobs').json()['jobs'], [])
            self.assertEqual(client.get('/api/jobs?applied=applied').json()['jobs'][0]['job_id'], 'graduate')
            self.assertEqual(client.delete('/api/jobs/graduate').status_code, 200)
            self.assertEqual(client.get('/api/jobs?sort=invalid').status_code, 422)
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
