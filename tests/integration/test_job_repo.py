import pytest
from sqlalchemy.orm import Session
from jobhunter.db.models import Job
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.repos.job import JobRepo


@pytest.fixture
def job_repo(db_session: Session) -> JobRepo:
    return JobRepo(db_session)


def test_create_and_retrieve_roundtrip(job_repo: JobRepo) -> None:
    # Given
    job = Job(
        source="linkedin",
        url="https://linkedin.com/jobs/123",
        url_hash="hash123",
        title="Software Engineer",
        company="Tech Corp",
        description="We are looking for a dev",
    )

    # When
    created_job = job_repo.create(job)
    job_id = created_job.id
    retrieved_job = job_repo.get(job_id)

    # Then
    assert retrieved_job is not None
    assert retrieved_job.id == job_id
    assert retrieved_job.title == "Software Engineer"
    assert retrieved_job.url_hash == "hash123"


def test_find_by_url_hash_returns_none_when_missing(job_repo: JobRepo) -> None:
    # When
    job = job_repo.find_by_url_hash("nonexistent")

    # Then
    assert job is None


def test_find_by_url_hash_returns_job(job_repo: JobRepo, sample_job: Job) -> None:
    # When
    found_job = job_repo.find_by_url_hash(sample_job.url_hash)

    # Then
    assert found_job is not None
    assert found_job.url_hash == sample_job.url_hash


def test_bulk_create_dedupes_by_url_hash(job_repo: JobRepo) -> None:
    # Given
    jobs = [
        Job(source="src", url="u1", url_hash="h1", title="T1", company="C1", description="D1"),
        Job(source="src", url="u2", url_hash="h2", title="T2", company="C2", description="D2"),
        Job(source="src", url="u3", url_hash="h3", title="T3", company="C3", description="D3"),
        Job(
            source="src", url="u4", url_hash="h1", title="T1-dup", company="C1", description="D1"
        ),  # Duplicate hash
        Job(source="src", url="u5", url_hash="h5", title="T5", company="C5", description="D5"),
    ]

    # When
    inserted_ids = job_repo.bulk_create_skipping_duplicates(jobs)

    # Then
    assert len(inserted_ids) == 4
    all_jobs = job_repo.list()
    # Note: if sample_job is also in DB because of other tests/fixtures,
    # we might need to be careful. But fixtures are usually per test.
    # In this test, we only created these 5 (4 unique).
    # Wait, the session might already have sample_job if it was used in another test?
    # No, each test gets a fresh transactional session that rolls back.
    # But wait, if job_repo.list() is called, it returns ALL jobs in the current session/transaction.
    assert len(all_jobs) == 4
    hashes = [j.url_hash for j in all_jobs]
    assert "h1" in hashes
    assert "h2" in hashes
    assert "h3" in hashes
    assert "h5" in hashes


def test_list_by_status_filter(job_repo: JobRepo) -> None:
    # Given
    job1 = Job(
        source="s",
        url="u1",
        url_hash="h1",
        title="T1",
        company="C1",
        description="D",
        status=JobStatus.NEW,
    )
    job2 = Job(
        source="s",
        url="u2",
        url_hash="h2",
        title="T2",
        company="C2",
        description="D",
        status=JobStatus.APPLIED,
    )
    job3 = Job(
        source="s",
        url="u3",
        url_hash="h3",
        title="T3",
        company="C3",
        description="D",
        status=JobStatus.NEW,
    )
    job_repo.create(job1)
    job_repo.create(job2)
    job_repo.create(job3)

    # When
    new_jobs = job_repo.list_by_status(JobStatus.NEW)

    # Then
    assert len(new_jobs) == 2
    for j in new_jobs:
        assert j.status == JobStatus.NEW


def test_mark_status_updates_field_and_timestamp(job_repo: JobRepo, sample_job: Job) -> None:
    # Given
    job_id = sample_job.id
    initial_scraped_at = sample_job.scraped_at

    # When
    job_repo.mark_status(job_id, JobStatus.APPLIED)

    # Then
    updated_job = job_repo.get(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.APPLIED
    assert updated_job.scraped_at == initial_scraped_at


def test_update_generic(job_repo: JobRepo, sample_job: Job) -> None:
    # Given
    job_id = sample_job.id

    # When
    job_repo.update(job_id, title="Senior Software Engineer", tier=JobTier.A)

    # Then
    updated_job = job_repo.get(job_id)
    assert updated_job is not None
    assert updated_job.title == "Senior Software Engineer"
    assert updated_job.tier == JobTier.A


def test_delete_generic(job_repo: JobRepo, sample_job: Job) -> None:
    # Given
    job_id = sample_job.id

    # When
    deleted = job_repo.delete(job_id)

    # Then
    assert deleted is True
    assert job_repo.get(job_id) is None
