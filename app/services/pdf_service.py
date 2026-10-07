"""
app/services/pdf_service.py
---------------------------
Service responsible solely for PDF generation.

This module is completely decoupled from the database (SQLAlchemy) and the
web framework (FastAPI). It takes raw data and returns a file path.
This separation of concerns makes it easy to test in isolation.
"""

import io
import os
from datetime import date
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

# ── Constants ──────────────────────────────────────────────────────────────────
# Path to the static template generated in Phase 6.
TEMPLATE_PATH = Path("templates") / "certificate_template.pdf"


def generate_certificate_pdf(
    recipient_name: str,
    certificate_title: str,
    course_name: str,
    organization: str,
    issue_date: date,
    certificate_id: str,
    output_dir: Path,
) -> str:
    """
    Generate a final certificate PDF by overlaying dynamic text onto the static template.

    Args:
        recipient_name: Name of the person receiving the certificate.
        certificate_title: E.g. 'Certificate of Completion'.
        course_name: Name of the course/event.
        organization: Issuing body.
        issue_date: Date of issue.
        certificate_id: Unique UUID string for verification.
        output_dir: Directory where the final PDF should be saved.

    Returns:
        The relative file path to the generated PDF (e.g. "generated/job-uuid/cert-uuid.pdf").

    Raises:
        FileNotFoundError: If the static template does not exist.
        IOError: If writing to the output directory fails.
    """
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(
            f"Certificate template not found at {TEMPLATE_PATH}. "
            "Ensure the template was generated in Phase 6."
        )

    # 1. Ensure the output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # 2. Define the output file path
    # We use the certificate_id as the filename for uniqueness.
    output_filename = f"{certificate_id}.pdf"
    output_path = output_dir / output_filename

    # 3. Create the dynamic overlay using ReportLab
    # Instead of writing the overlay to disk, we write it to an in-memory buffer.
    packet = io.BytesIO()

    # Use landscape A4 (matches the template)
    width, height = landscape(A4)
    c = canvas.Canvas(packet, pagesize=(width, height))

    # --- Draw dynamic text ---

    # Certificate Title (e.g. "Certificate of Completion")
    c.setFont("Helvetica-Bold", 32)
    c.setFillColor(HexColor("#111827"))  # Dark gray/black
    c.drawCentredString(width / 2, height / 2 + 80, certificate_title.upper())

    # Recipient Name
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(HexColor("#1E3A8A"))  # Dark blue
    c.drawCentredString(width / 2, height / 2, recipient_name)

    # Course / Event Name
    c.setFont("Helvetica-Bold", 20)
    c.setFillColor(HexColor("#111827"))
    c.drawCentredString(width / 2, height / 2 - 90, course_name)

    # Organization
    c.setFont("Helvetica-Oblique", 14)
    c.setFillColor(HexColor("#4B5563"))
    c.drawCentredString(width / 2, height / 2 - 120, f"Issued by {organization}")

    # Dynamic Date (bottom right, above the static "Date of Issue" line)
    margin = 40
    sig_y = margin + 60
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(HexColor("#111827"))
    c.drawCentredString(
        width - margin - 180, sig_y + 10, issue_date.strftime("%B %d, %Y")
    )

    # Certificate ID (bottom left, next to the static label)
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#6B7280"))
    c.drawString(margin + 75, margin + 15, certificate_id)

    c.save()

    # Move the buffer cursor to the beginning
    packet.seek(0)

    # 4. Merge the overlay with the static template using pypdf
    new_pdf = PdfReader(packet)
    existing_pdf = PdfReader(open(TEMPLATE_PATH, "rb"))

    # The output writer
    output = PdfWriter()

    # Grab the single page from the template
    page = existing_pdf.pages[0]

    # Merge the overlay page onto the template page
    page.merge_page(new_pdf.pages[0])

    # Add the merged page to our output
    output.add_page(page)

    # 5. Write the final PDF to disk
    with open(output_path, "wb") as outputStream:
        output.write(outputStream)

    # Return the relative path as a string (this gets stored in the DB)
    return os.path.relpath(output_path)
