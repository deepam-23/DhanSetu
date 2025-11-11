import io
import hashlib
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from flask import current_app
import qrcode
from reportlab.lib.utils import ImageReader


def generate_kyc_pdf(kyc_data: dict, qr_text: str) -> tuple[bytes, str]:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, height - 50, "KYC Verification Document")

    c.setFont("Helvetica", 11)
    y = height - 100
    for k, v in kyc_data.items():
        c.drawString(50, y, f"{k}: {v}")
        y -= 18

    img = qrcode.make(qr_text)
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)
    qr_image = ImageReader(img_buf)
    c.drawImage(qr_image, width - 200, 50, 150, 150)

    c.showPage()
    c.save()

    pdf_bytes = buf.getvalue()
    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    return pdf_bytes, checksum
