# Production-ready Dockerfile for Flask app using Gunicorn
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps for Pillow/ReportLab/pikepdf/pytesseract
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    tesseract-ocr \
    qpdf \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libfreetype6-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the rest of the app
COPY . .

# Flask instance and storage directories (if needed at runtime)
RUN mkdir -p /app/instance /app/storage

EXPOSE 8000
ENV PORT=8000

# Gunicorn entrypoint using app from run.py (create_app already invoked there)
CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:8000", "--workers", "3"]
