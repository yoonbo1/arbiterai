FROM python:3.12-slim
# tesseract-ocr pulls in the English traineddata (tesseract-ocr-eng).
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Presidio's default configuration expects en_core_web_lg (~560 MB). A dev build can pass
# --build-arg SPACY_MODEL=en_core_web_sm; the worker's SPACY_MODEL env must then match.
ARG SPACY_MODEL=en_core_web_lg
RUN python -m spacy download ${SPACY_MODEL}
ENV SPACY_MODEL=${SPACY_MODEL}
COPY . ./worker
STOPSIGNAL SIGTERM
CMD ["python", "-m", "worker.main"]
