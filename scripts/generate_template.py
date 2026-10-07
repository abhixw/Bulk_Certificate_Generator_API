"""
generate_template.py
--------------------
Generates the static base certificate template for the Bulk Certificate Generator.
This creates `templates/certificate_template.pdf` which will be used by the
PDF generation service to overlay dynamic text.
"""

import os

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas


def create_template(output_path: str):
    # Use landscape A4 for certificates
    width, height = landscape(A4)
    c = canvas.Canvas(output_path, pagesize=(width, height))

    # ── Background ────────────────────────────────────────────────────────────
    # Light cream/off-white background
    c.setFillColor(HexColor("#F9F9F6"))
    c.rect(0, 0, width, height, stroke=0, fill=1)

    # ── Borders ───────────────────────────────────────────────────────────────
    # Outer dark blue border
    margin = 40
    c.setStrokeColor(HexColor("#1E3A8A"))
    c.setLineWidth(4)
    c.rect(margin, margin, width - 2 * margin, height - 2 * margin)

    # Inner gold border
    inner_margin = 52
    c.setStrokeColor(HexColor("#D97706"))
    c.setLineWidth(1.5)
    c.rect(
        inner_margin, inner_margin, width - 2 * inner_margin, height - 2 * inner_margin
    )

    # ── Static Text / Design Elements ─────────────────────────────────────────
    # A decorative top element
    c.setFillColor(HexColor("#1E3A8A"))
    c.rect(width / 2 - 100, height - margin - 20, 200, 20, stroke=0, fill=1)

    # "CERTIFICATE" header background shadow effect (static design)
    # The actual dynamic title will be placed slightly below this, or we can leave
    # the title dynamic as requested. The spec says:
    # "Dynamic fields should include: recipient name, certificate title, course/event name, organization, issue date, certificate ID"

    # Let's add some static text that won't change
    c.setFont("Helvetica-Oblique", 14)
    c.setFillColor(HexColor("#6B7280"))
    c.drawCentredString(width / 2, height / 2 + 40, "This is to certify that")

    c.drawCentredString(
        width / 2, height / 2 - 50, "has successfully completed the program"
    )

    # Signature lines
    sig_y = margin + 60
    c.setStrokeColor(HexColor("#9CA3AF"))
    c.setLineWidth(1)

    # Left signature line
    c.line(margin + 80, sig_y, margin + 280, sig_y)
    c.setFont("Helvetica", 10)
    c.drawCentredString(margin + 180, sig_y - 15, "Authorized Signature")

    # Right date line (this is static text; the dynamic date will go above it)
    c.line(width - margin - 280, sig_y, width - margin - 80, sig_y)
    c.drawCentredString(width - margin - 180, sig_y - 15, "Date of Issue")

    # Certificate ID static label
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#9CA3AF"))
    c.drawString(margin + 15, margin + 15, "Certificate ID: ")

    c.save()
    print(f"✅ Template generated at: {output_path}")


if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    create_template("templates/certificate_template.pdf")
