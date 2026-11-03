# The clean room image: only what's needed to read invoices. No shell tools beyond the base, no network at run time.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pymupdf==1.24.10 python-docx==1.1.2 pillow==10.4.0 pytesseract==0.3.13
USER 65534:65534
WORKDIR /tmp
