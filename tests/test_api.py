"""
tests/test_api.py
-----------------
Unit tests for the FastAPI application.

We use TestClient to test the HTTP layer. We mock the background worker
to ensure tests run instantly and don't require filesystem/PDF dependencies.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Create a single TestClient instance for all tests
client = TestClient(app)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_worker():
    """
    Mock the background worker so it doesn't actually try to generate PDFs
    or write to the database during API tests.
    """
    with patch("app.api.jobs.process_job") as mock:
        yield mock


# ── Tests: Request Validation ──────────────────────────────────────────────────


def test_create_job_valid_request(mock_worker):
    """Test that a valid request is accepted (HTTP 202)."""
    payload = {
        "certificate_title": "Unit Test Cert",
        "course_name": "Testing 101",
        "organization": "Test Org",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ],
    }
    response = client.post("/api/jobs/", json=payload)

    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["status"] == "PENDING"
    assert data["total_count"] == 2

    # Ensure the background worker was triggered with the job UUID
    mock_worker.assert_called_once()


def test_create_job_invalid_email(mock_worker):
    """Test that invalid emails are rejected (HTTP 422)."""
    payload = {
        "certificate_title": "Unit Test Cert",
        "course_name": "Testing 101",
        "organization": "Test Org",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "Alice", "email": "not-an-email"}],
    }
    response = client.post("/api/jobs/", json=payload)

    assert response.status_code == 422
    assert "is not a valid email address" in response.text

    mock_worker.assert_not_called()


def test_create_job_duplicate_email(mock_worker):
    """Test that duplicate emails in the same batch are rejected."""
    payload = {
        "certificate_title": "Unit Test Cert",
        "course_name": "Testing 101",
        "organization": "Test Org",
        "issue_date": "2026-10-07",
        "recipients": [
            {"name": "Alice", "email": "duplicate@example.com"},
            {"name": "Bob", "email": "DUPLICATE@example.com"},
        ],
    }
    response = client.post("/api/jobs/", json=payload)

    assert response.status_code == 422
    assert "Duplicate recipient email(s)" in response.text

    mock_worker.assert_not_called()


def test_create_job_missing_fields(mock_worker):
    """Test that missing required fields are caught."""
    payload = {
        "certificate_title": "Unit Test Cert",
        # missing course_name
        "organization": "Test Org",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "Alice", "email": "alice@example.com"}],
    }
    response = client.post("/api/jobs/", json=payload)

    assert response.status_code == 422
    assert "course_name" in response.text

    mock_worker.assert_not_called()


# ── Tests: Get Job Status ──────────────────────────────────────────────────────


def test_get_job_status_not_found():
    """Test that requesting a non-existent job returns 404."""
    response = client.get("/api/jobs/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    data = response.json()
    assert data["detail"]["error"]["code"] == "JOB_NOT_FOUND"


def test_create_and_get_job(mock_worker):
    """End-to-end test: Create a job, then fetch its status."""
    payload = {
        "certificate_title": "Unit Test Cert",
        "course_name": "Testing 101",
        "organization": "Test Org",
        "issue_date": "2026-10-07",
        "recipients": [{"name": "Alice", "email": "alice@example.com"}],
    }

    # 1. Create the job
    create_response = client.post("/api/jobs/", json=payload)
    assert create_response.status_code == 202
    job_id = create_response.json()["id"]

    # 2. Fetch its status
    status_response = client.get(f"/api/jobs/{job_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()

    assert status_data["id"] == job_id
    assert status_data["status"] == "PENDING"
    assert status_data["total_count"] == 1
    # Check computed fields
    assert status_data["pending_count"] == 1
    assert status_data["progress"] == 0.0

    # 3. Fetch its certificates list
    certs_response = client.get(f"/api/jobs/{job_id}/certificates")
    assert certs_response.status_code == 200
    certs_data = certs_response.json()

    assert len(certs_data["certificates"]) == 1
    cert = certs_data["certificates"][0]
    assert cert["recipient_name"] == "Alice"
    assert cert["status"] == "PENDING"
    # download_url should be None because it's not COMPLETED
    assert cert["download_url"] is None
