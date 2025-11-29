import io
import os
import hashlib
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from flask import current_app
import qrcode
from reportlab.lib.utils import ImageReader
from qrcode.constants import ERROR_CORRECT_H


def generate_kyc_pdf(kyc_data: dict, qr_text: str, selfie_path: str | None = None) -> tuple[bytes, str]:
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

    # Optional selfie in top-right
    if selfie_path and os.path.exists(selfie_path):
        try:
            print(f"PDF service: Adding selfie from path: {selfie_path}")
            selfie_reader = ImageReader(selfie_path)
            c.drawImage(selfie_reader, width - 220, height - 260, 170, 170, preserveAspectRatio=True, mask='auto')
            c.setFont("Helvetica", 9)
            c.drawString(width - 220, height - 270, "Photo")
        except Exception as e:
            print(f"PDF service: Error adding selfie: {e}")
            pass
    else:
        if selfie_path:
            print(f"PDF service: Selfie path provided but file not found: {selfie_path}")
        else:
            print("PDF service: No selfie path provided")

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_H,
        box_size=8,
        border=2,
    )
    qr.add_data(qr_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_buf.seek(0)
    qr_image = ImageReader(img_buf)
    c.drawImage(qr_image, width - 220, 50, 170, 170, mask='auto')

    c.showPage()
    c.save()

    pdf_bytes = buf.getvalue()
    checksum = hashlib.sha256(pdf_bytes).hexdigest()
    return pdf_bytes, checksum
