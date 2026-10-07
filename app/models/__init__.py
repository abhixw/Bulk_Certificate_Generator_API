"""
app/models/__init__.py
----------------------
Re-exports all ORM models from this package.

Why this matters
----------------
SQLAlchemy's `Base.metadata.create_all()` only knows about tables whose
model classes have been *imported* before it is called.  If a model is
never imported, its table definition never registers with `Base.metadata`
and the table is silently skipped.

By importing every model here, any module that does:

    from app.models import GenerationJob, Certificate

or even just:

    import app.models  # side-effect import

guarantees that ALL tables are registered with `Base.metadata`.

The lifespan in `app/main.py` does `import app.models` before calling
`Base.metadata.create_all(engine)` for exactly this reason.
"""

from app.models.certificate import Certificate, CertificateStatus
from app.models.job import GenerationJob, JobStatus

__all__ = [
    "GenerationJob",
    "JobStatus",
    "Certificate",
    "CertificateStatus",
]
