# Bulk Certificate Generator API

A production-quality Python backend API for bulk generation of PDF certificates. Built with FastAPI, PostgreSQL, SQLAlchemy 2.0, and ReportLab.

## 🏗 Architecture

The system is designed to handle bulk certificate generation asynchronously without relying on heavy message brokers like Celery, RabbitMQ, or Redis. It uses **FastAPI BackgroundTasks** for simple, in-memory worker management, making it extremely easy to deploy while maintaining responsiveness.

- **Web Framework**: FastAPI
- **Database**: PostgreSQL (Neon) via `psycopg 3`
- **ORM**: SQLAlchemy 2.0 (Synchronous engine to match the background worker's CPU-bound PDF generation)
- **PDF Generation**: `reportlab` (Dynamic text overlay) + `pypdf` (Merging with static template)
- **Validation**: Pydantic v2
- **Testing**: Pytest + FastAPI TestClient

### Workflow
1. Client submits a job containing batch metadata and an array of recipients.
2. The API inserts a `GenerationJob` and `N` `Certificate` rows in a single atomic transaction.
3. The API immediately returns HTTP `202 Accepted`.
4. A FastAPI BackgroundTask picks up the job ID and opens a fresh DB session.
5. The worker iterates sequentially, generating PDFs in memory and merging them onto a predefined template.
6. Progress is tracked incrementally in $O(1)$ time by updating integer counters directly on the `GenerationJob` row after every certificate.
7. Clients poll the API for progress and can download the PDFs when they are `COMPLETED`.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.12+
- PostgreSQL database (Local or Cloud like Neon/Supabase)

### 1. Installation

Clone the repository and install dependencies inside a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory:

```env
# PostgreSQL connection string (must use postgresql+psycopg://)
DATABASE_URL="postgresql+psycopg://user:password@host/dbname?sslmode=require"
```

### 3. Generate the Certificate Template

Before running the API, generate the static base PDF template. This template will be overlaid with dynamic data.

```bash
python scripts/generate_template.py
```
*This creates `templates/certificate_template.pdf`.*

### 4. Run the API

```bash
uvicorn app.main:app --reload
```
The API will be available at `http://127.0.0.1:8000`.

---

## 📖 API Endpoints

Interactive Swagger UI documentation is available at `http://127.0.0.1:8000/docs`.

### 1. Create a Bulk Generation Job
`POST /api/jobs/`

Creates a new job and queues the certificates for generation.
Accepts up to 500 recipients per request. Duplicate emails are automatically rejected.

**Example Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/jobs/ \
  -H "Content-Type: application/json" \
  -d '{
    "certificate_title": "Certificate of Completion",
    "course_name": "Python Backend Development",
    "organization": "ABC Technologies",
    "issue_date": "2026-10-07",
    "recipients": [
      {
        "name": "Alice Smith",
        "email": "alice@example.com"
      }
    ]
  }'
```

**Example Response (202 Accepted):**
```json
{
  "id": "24493f55-caa5-4956-b71c-3b0fc5c8a0bb",
  "status": "PENDING",
  "total_count": 1
}
```

### 2. Get Job Status (Progress)
`GET /api/jobs/{job_id}`

Poll this endpoint to monitor the worker's progress. It computes the `progress` percentage dynamically in $O(1)$ time.

**Example Request:**
```bash
curl http://127.0.0.1:8000/api/jobs/24493f55-caa5-4956-b71c-3b0fc5c8a0bb
```

**Example Response (200 OK):**
```json
{
  "id": "24493f55-caa5-4956-b71c-3b0fc5c8a0bb",
  "status": "PROCESSING",
  "total_count": 100,
  "completed_count": 73,
  "failed_count": 2,
  "pending_count": 25,
  "progress": 75.0
}
```

### 3. List Job Certificates
`GET /api/jobs/{job_id}/certificates`

Returns the individual status of every certificate in the batch. If a certificate is completed, a `download_url` is provided.

**Example Request:**
```bash
curl http://127.0.0.1:8000/api/jobs/24493f55-caa5-4956-b71c-3b0fc5c8a0bb/certificates
```

### 4. Download a Certificate
`GET /api/certificates/{certificate_id}/download`

Streams the generated PDF file to the client. Can be used directly in browser `<a>` tags.

**Example Request:**
```bash
curl -O http://127.0.0.1:8000/api/certificates/b10b483c-3339-474d-bd4f-e432c2ac53d1/download
```

---

## 🧪 Testing

The unit tests are written with `pytest` and mock out the background worker to ensure blazing-fast execution without requiring filesystem I/O.

```bash
pytest tests/ -v
```
