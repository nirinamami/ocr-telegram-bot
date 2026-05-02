FROM python:3.9-slim

# 1. AJOUTER LES DÉPENDANCES SYSTÈME (Indispensable pour l'OCR)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    poppler-utils \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Render utilise le port 10000 par défaut
EXPOSE 10000

CMD ["python", "app.py"]
