from jobs.education_filter import education_matches
from jobs.experience_filter import experience_matches
from jobs.contract_filter import contract_matches
from jobs.graduation_filter import graduation_matches
from jobs.student_filter import student_matches
from jobs.location_filter import location_matches, location_needs_description
from jobs.domain_filter import domain_matches


def _qualifications_match(job: dict) -> bool:
    return (student_matches(job) and experience_matches(job) and education_matches(job)
            and graduation_matches(job) and contract_matches(job))


def pre_description_matches(job: dict) -> bool:
    """Allow ambiguous remote listings to establish UK eligibility in the detail."""
    return (_qualifications_match(job) and domain_matches(job)
            and (location_matches(job) or location_needs_description(job)))


def profile_matches(job: dict) -> bool:
    """Apply all candidate constraints to both fetched and stored listings."""
    return _qualifications_match(job) and location_matches(job) and domain_matches(job)
