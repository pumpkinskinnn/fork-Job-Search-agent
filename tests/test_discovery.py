"""Discovery coverage and budgets, using mocks only (no providers or live HTTP)."""

import unittest

from tests.legacy_candidate import BscCandidateTestCase
from unittest.mock import Mock, patch

import config
from jobs import career_fetcher, domain_filter, job_fetcher, linkedin_client
from jobs.ats import details, workday
from jobs.company_utils import role_matches
from jobs.profile_filter import profile_matches

ROLES = config.DEFAULT_TARGET_ROLES.split(",")
COMPANIES = ["Octopus Energy", "EDF", "National Grid", "Johnson Matthey", "Arup"]
# Keep the original fourteen-query scenario stable as the live order evolves.
QUERIES = ("graduate energy,energy analyst,renewable energy graduate,sustainability graduate,"
           "materials graduate,materials scientist,battery scientist,electrochemistry,"
           "graduate scientist,research scientist,clean energy graduate,net zero graduate,"
           "graduate engineer,technical analyst").split(",")


class TitleAndDomainTests(BscCandidateTestCase):
    def test_requested_titles_survive_prefilter(self):
        for title in (
            "Clean Technology Graduate", "Net Zero Graduate Programme", "Graduate Development Programme",
            "Chemical Engineer", "Graduate Chemical Engineer", "Energy Graduate Programme",
            "Sustainability Graduate Programme", "Environmental Graduate", "Decarbonisation Analyst",
            "Low Carbon Analyst", "Climate Analyst", "Energy Transition Analyst", "Graduate Consultant",
            "Graduate Engineer", "Process Engineer", "Research Assistant", "Research Associate",
            "Laboratory Scientist", "Materials Researcher", "Battery Researcher",
        ):
            with self.subTest(title=title):
                self.assertTrue(role_matches(title, ROLES))

    def test_senior_and_non_stem_titles_are_rejected(self):
        for title in ("Senior Energy Consultant", "Lead Process Engineer", "Marketing Graduate Scheme",
                      "Graduate HR Analyst", "Senior Chemical Engineer", "Graduate Software Engineer",
                      "Retail Graduate Scheme", "Sales Analyst"):
            with self.subTest(title=title):
                self.assertFalse(role_matches(title, ROLES))

    def test_generic_titles_require_domain_evidence_when_description_exists(self):
        for title, text in (
            ("Graduate Development Programme", "Analyse energy transition scenarios."),
            ("Graduate Consultant", "Provide renewable energy advice."),
            ("Graduate Analyst", "Use data to model sustainability outcomes."),
            ("Graduate Engineer", "Develop electrochemistry experiments."),
            ("Research Scientist", "Investigate functional materials."),
            ("Research Assistant", "Research battery-materials interfaces."),
            ("Laboratory Scientist", "Measure chemistry and polymer synthesis."),
        ):
            with self.subTest(title=title):
                job = {"title": title, "description": text, "location": "London, UK"}
                self.assertTrue(profile_matches(job))
                job["description"] = "<p>Manage payroll and banking records.</p>"
                self.assertFalse(domain_filter.domain_matches(job))

    def test_missing_description_retained_as_uncertain(self):
        for missing in ("", "Job description unavailable."):
            job = {"title": "Graduate Consultant", "description": missing, "location": "London, UK"}
            self.assertTrue(profile_matches(job))
            self.assertFalse(domain_filter.description_available(job))


class LinkedInDiscoveryTests(BscCandidateTestCase):
    def setUp(self):
        super().setUp()
        for name, value in (
            ("USER_PROFILE", {"target_roles": ROLES, "filter_by_role": True}),
            ("_company_offset", 0), ("_broad_offset", 0), ("_role_offset", 0),
            ("_known_job_ids", set()), ("_known_descriptions", {}),
            ("ENABLE_BROAD_LINKEDIN_SEARCH", True), ("BROAD_SEARCH_QUERIES", QUERIES),
            ("BROAD_SEARCH_QUERIES_PER_CYCLE", 4), ("LINKEDIN_MAX_SEARCHES_PER_CYCLE", 20),
        ):
            patcher = patch.object(job_fetcher, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, value in (
            ("jobs.job_store.get_existing_job_ids", set()),
            ("jobs.job_store.get_existing_job_descriptions", {}),
            ("jobs.job_fetcher.linkedin_is_limited", False),
        ):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cycle(self, companies, fetch):
        with patch.object(job_fetcher, "_fetch_search", side_effect=fetch) as search, \
             patch.object(job_fetcher, "attach_description"):
            result = job_fetcher._fetch_linkedin_jobs(companies, ROLES, "London, United Kingdom", "r604800")
        return result, search

    def test_broad_discovery_without_shortlist_accepts_unknown_company(self):
        job = {"job_id": "li_123", "title": "Graduate Consultant", "company": "New Cleantech Employer",
               "location": "London, UK", "description": "Analyse renewable energy."}
        result, search = self.run_cycle([], lambda *args: [job])
        self.assertEqual(result, [job])  # deduplicated across queries
        self.assertEqual([call.args[0] for call in search.call_args_list], QUERIES[:4])
        for call in search.call_args_list:
            self.assertEqual(call.args[1], "London, United Kingdom")

    def test_company_searches_and_independent_searches_both_run(self):
        company_job = {"job_id": "li_1", "title": "Energy Analyst", "company": "Octopus Energy",
                       "location": "London", "description": "Energy analysis."}
        broad_job = dict(company_job, job_id="li_2", company="Unlisted Employer")
        result, search = self.run_cycle(COMPANIES, lambda query, *args: [company_job] if query in COMPANIES else [broad_job])
        self.assertEqual([job["job_id"] for job in result], ["li_1", "li_2"])
        self.assertEqual([call.args[0] for call in search.call_args_list], COMPANIES + QUERIES[:4])

    def test_broad_results_use_candidate_titles_not_exact_query_wording(self):
        job = {"job_id": "li_1", "title": "Battery Researcher", "location": "London", "company": "New Employer"}
        with patch.object(job_fetcher, "_fetch_search", return_value=[job]), \
             patch.object(job_fetcher, "attach_description"):
            self.assertEqual(job_fetcher.fetch_jobs_for_role("electrochemistry", "London, United Kingdom", "r604800"), [job])

    def test_searches_precede_description_requests(self):
        events = []
        def fetch(query, *args):
            events.append('search')
            return [{"job_id": query, "title": "Energy Analyst", "company": "New Employer", "location": "London"}]
        with patch.object(job_fetcher, "_fetch_search", side_effect=fetch), \
             patch.object(job_fetcher, "attach_description", side_effect=lambda job: events.append('detail')):
            job_fetcher._fetch_linkedin_jobs([], ROLES, "London, United Kingdom", "r604800")
        self.assertEqual(events, ['search'] * 4 + ['detail'] * 4)

    def test_detail_enrichment_gives_each_query_a_turn(self):
        def fetch(query, *args):
            return [{'job_id': f'{query}:{i}', 'title': 'Energy Analyst', 'company': 'New Employer',
                     'location': 'London'} for i in range(2)]
        with patch.object(job_fetcher, '_fetch_search', side_effect=fetch), \
             patch.object(job_fetcher, 'attach_description') as attach:
            job_fetcher._fetch_linkedin_jobs([], ROLES, 'London, United Kingdom', 'r604800')
        self.assertEqual([call.args[0]['job_id'] for call in attach.call_args_list],
                         [f'{query}:{i}' for i in range(2) for query in QUERIES[:4]])

    def test_uk_remote_description_is_fetched_before_final_location_check(self):
        job = {'job_id': 'li_remote', 'title': 'Graduate Consultant', 'company': 'New Employer', 'location': 'Remote'}
        def attach(job):
            job['description'] = 'UK remote position analysing renewable energy.'
        with patch.object(job_fetcher, 'attach_description', side_effect=attach) as fetch:
            self.assertTrue(job_fetcher._is_relevant(job, '', ROLES))
        fetch.assert_called_once()

    def test_rotation_and_combined_search_cap(self):
        actual = []
        for cycle in range(4):
            _, search = self.run_cycle(COMPANIES, lambda *args: [])
            actual.append([call.args[0] for call in search.call_args_list if call.args[0] not in COMPANIES])
            self.assertEqual(search.call_count, 9)
        self.assertEqual(actual, [QUERIES[:4], QUERIES[4:8], QUERIES[8:12], QUERIES[12:] + QUERIES[:2]])
        with patch.object(job_fetcher, "LINKEDIN_MAX_SEARCHES_PER_CYCLE", 6), \
             patch.object(job_fetcher, "_company_offset", 0):
            for expected in (("Octopus Energy", "EDF"), ("National Grid", "Johnson Matthey")):
                _, search = self.run_cycle(COMPANIES, lambda *args: [])
                self.assertEqual(search.call_count, 6)
                self.assertEqual(tuple(call.args[0] for call in search.call_args_list[:2]), expected)

    def test_unattempted_broad_queries_are_not_skipped_on_block(self):
        with patch.object(job_fetcher, "linkedin_is_limited", side_effect=[False, True]):
            _, search = self.run_cycle([], lambda *args: [])
        self.assertEqual(search.call_count, 1)
        self.assertEqual(job_fetcher.linkedin_search_plan([], ROLES)[0], ('broad', QUERIES[1]))

    def test_broad_discovery_can_be_disabled_and_role_fallback_rotates(self):
        with patch.object(job_fetcher, "ENABLE_BROAD_LINKEDIN_SEARCH", False):
            _, search = self.run_cycle(COMPANIES, lambda *args: [])
            self.assertEqual(search.call_count, 5)
            self.run_cycle([], lambda *args: [])
            self.assertEqual(job_fetcher.linkedin_search_plan([], ROLES)[0], ('role', ROLES[20]))

    def test_cached_descriptions_reused_and_domain_checked(self):
        with patch.object(job_fetcher, "_known_job_ids", {'li_1'}), \
             patch.object(job_fetcher, "_known_descriptions", {'li_1': 'Payroll and banking.'}), \
             patch.object(job_fetcher, "attach_description") as attach:
            self.assertFalse(job_fetcher._is_relevant(
                {'job_id': 'li_1', 'title': 'Graduate Consultant', 'location': 'London'}, '', ROLES))
        attach.assert_not_called()

    def test_rate_defaults_unchanged(self):
        self.assertEqual(config.LINKEDIN_MIN_DELAY_SECONDS, 6)
        self.assertEqual(config.LINKEDIN_MAX_REQUESTS_PER_MINUTE, 10)
        self.assertEqual(config.LINKEDIN_MAX_REQUESTS_PER_HOUR, 80)
        self.assertEqual(config.LINKEDIN_MAX_SEARCHES_PER_CYCLE, 20)
        self.assertEqual(linkedin_client._MAX_REQUESTS_PER_CYCLE, 40)
        self.assertEqual(config.CHECK_INTERVAL_MINUTES, 15)
        self.assertEqual(config.FETCH_CONCURRENCY, 8)


class ATSDiscoveryTests(BscCandidateTestCase):
    def setUp(self):
        super().setUp()
        self.cached = patch('jobs.job_store.get_existing_job_descriptions', return_value={})
        self.cached.start()
        self.addCleanup(self.cached.stop)
        for module, name, value in ((details, '_offsets', {}), (workday, '_search_offsets', {})):
            patcher = patch.object(module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_workday_one_rotating_term_per_board_with_existing_pagination(self):
        session = Mock()
        session.post.return_value.json.return_value = {"total": 0, "jobPostings": []}
        with patch.object(workday, "WORKDAY_SEARCH_TERMS", ['graduate', 'energy', 'materials']), \
             patch.object(workday, "get_session", return_value=session):
            for _ in range(4):
                workday.fetch_workday_jobs('Example', 'example.wd5.myworkdayjobs.com/Careers')
            workday.fetch_workday_jobs('Other', 'other.wd1.myworkdayjobs.com/Jobs')
        payloads = [call.kwargs['json'] for call in session.post.call_args_list]
        self.assertEqual([payload['searchText'] for payload in payloads], ['graduate', 'energy', 'materials', 'graduate', 'graduate'])
        self.assertTrue(all(payload['limit'] == 20 and payload['offset'] == 0 for payload in payloads))
        self.assertEqual(workday.MAX_JOBS, 400)

    def test_workday_term_does_not_rotate_between_pages_and_cap_remains_20_pages(self):
        session = Mock()
        session.post.return_value.json.return_value = {'total': 1000, 'jobPostings': [
            {'title': 'Materials Scientist', 'externalPath': '/job/1', 'locationsText': 'London'}]}
        with patch.object(workday, 'get_session', return_value=session), \
             patch.object(workday, 'WORKDAY_SEARCH_TERMS', ['materials', 'energy']):
            workday.fetch_workday_jobs('Example', 'example.wd5.myworkdayjobs.com/Careers')
        self.assertEqual(session.post.call_count, 20)
        self.assertEqual({call.kwargs['json']['searchText'] for call in session.post.call_args_list}, {'materials'})

    def test_smartrecruiters_official_details_include_qualifications(self):
        job = {'source': 'smartrecruiters', 'job_url': 'https://api.smartrecruiters.com/v1/companies/Example/postings/123'}
        session = Mock()
        session.get.return_value.json.return_value = {'jobAd': {'sections': {
            'jobDescription': {'text': '<p>Analyse renewable energy.</p>'},
            'qualifications': {'text': '<p>BSc accepted. No previous experience required.</p>'}}}}
        with patch.object(details, 'get_session', return_value=session):
            description = details.fetch_official_description(job)
        self.assertIn('renewable energy', description)
        self.assertIn('BSc accepted', description)
        self.assertEqual(session.get.call_args.args[0], job['job_url'])
        self.assertFalse(session.get.call_args.kwargs['allow_redirects'])

    def test_smartrecruiters_detail_url_is_independent_of_public_job_link(self):
        from jobs.ats import smartrecruiters
        response = Mock()
        response.json.return_value = {'totalFound': 1, 'content': [
            {'id': '123', 'name': 'Graduate Consultant', 'location': {'city': 'London', 'country': 'gb'},
             'ref': 'https://jobs.smartrecruiters.com/Example/123-graduate-consultant'}]}
        with patch.object(smartrecruiters.requests, 'get', return_value=response):
            jobs = smartrecruiters.fetch_smartrecruiters_jobs('Example', 'Example', 'London, United Kingdom')
        self.assertTrue(jobs[0]['job_url'].startswith('https://jobs.smartrecruiters.com/'))
        self.assertEqual(details.official_detail_url(jobs[0]), 'https://api.smartrecruiters.com/v1/companies/Example/postings/123')

    def test_workday_official_job_detail_endpoint(self):
        job = {'source': 'workday', 'job_url': 'https://example.wd5.myworkdayjobs.com/Careers/job/London/Analyst_R123'}
        session = Mock()
        session.get.return_value.json.return_value = {'jobPostingInfo': {'jobDescription': '<p>Battery materials research.</p>'}}
        with patch.object(details, 'get_session', return_value=session):
            self.assertIn('Battery materials', details.fetch_official_description(job))
        self.assertEqual(session.get.call_args.args[0], 'https://example.wd5.myworkdayjobs.com/wday/cxs/example/Careers/job/London/Analyst_R123')

    def test_unsupported_detail_urls_never_fetch(self):
        with patch.object(details, 'get_session') as session:
            for url in ('https://example.com/job/123', 'http://example.wd5.myworkdayjobs.com/Careers/job/123',
                        'https://api.smartrecruiters.com:invalid/v1/companies/Example/postings/1',
                        'https://example.wd5.myworkdayjobs.com/Careers/job/../123'):
                self.assertEqual(details.fetch_official_description({'source': 'workday', 'job_url': url}), '')
        session.assert_not_called()

    def test_detail_budget_rotates_and_cache_avoids_requests(self):
        jobs = [{'source': 'smartrecruiters', 'company': 'Example', 'job_id': str(i),
                 'job_url': f'https://api.smartrecruiters.com/v1/companies/Example/postings/{i}'} for i in range(5)]
        with patch.object(details, 'fetch_official_description', return_value='') as fetch:
            details.enrich_ats_descriptions(jobs, limit=2)
            details.enrich_ats_descriptions(jobs, limit=2)
        self.assertEqual([call.args[0]['job_id'] for call in fetch.call_args_list], ['0', '1', '2', '3'])
        with patch('jobs.job_store.get_existing_job_descriptions', return_value={str(i): 'Energy research.' for i in range(5)}), \
             patch.object(details, 'fetch_official_description') as fetch:
            details.enrich_ats_descriptions(jobs, limit=2)
        fetch.assert_not_called()
        self.assertTrue(all(job['description'] == 'Energy research.' for job in jobs))

    def test_details_enable_generic_title_and_uk_remote_then_enforce_requirements(self):
        job = {'source': 'workday', 'job_id': 'wd_1', 'title': 'Graduate Consultant', 'company': 'Example',
               'location': 'Remote', 'job_url': 'https://example.wd5.myworkdayjobs.com/Careers/job/123'}
        with patch.object(career_fetcher, 'USER_PROFILE', {'filter_by_role': True, 'target_roles': ROLES}), \
             patch.object(career_fetcher, 'get_career_config', return_value={'ats': 'workday', 'slug': 'example'}), \
             patch.object(career_fetcher, '_fetch_from_ats', side_effect=lambda *args: [dict(job)]), \
             patch.object(details, 'fetch_official_description', return_value='UK remote role in renewable energy. BSc accepted.'):
            self.assertEqual(len(career_fetcher.fetch_career_jobs_for_company('Example')), 1)
        with patch.object(career_fetcher, 'USER_PROFILE', {'filter_by_role': True, 'target_roles': ROLES}), \
             patch.object(career_fetcher, 'get_career_config', return_value={'ats': 'workday', 'slug': 'example'}), \
             patch.object(career_fetcher, '_fetch_from_ats', side_effect=lambda *args: [dict(job)]), \
             patch.object(details, 'fetch_official_description', return_value='UK remote role in energy. PhD required.'):
            self.assertEqual(career_fetcher.fetch_career_jobs_for_company('Example'), [])

    def test_detail_failure_retains_eligible_london_job(self):
        import requests
        job = {'source': 'workday', 'job_id': 'wd_1', 'title': 'Graduate Consultant', 'company': 'Example',
               'location': 'London', 'job_url': 'https://example.wd5.myworkdayjobs.com/Careers/job/123'}
        session = Mock()
        session.get.side_effect = requests.Timeout('mock timeout')
        with patch.object(career_fetcher, 'USER_PROFILE', {'filter_by_role': True, 'target_roles': ROLES}), \
             patch.object(career_fetcher, 'get_career_config', return_value={'ats': 'workday', 'slug': 'example'}), \
             patch.object(career_fetcher, '_fetch_from_ats', return_value=[job]), \
             patch.object(details, 'get_session', return_value=session):
            self.assertEqual(career_fetcher.fetch_career_jobs_for_company('Example'), [job])
        self.assertFalse(domain_filter.description_available(job))


if __name__ == '__main__':
    unittest.main()
