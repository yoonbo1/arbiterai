# Local arm64-native replacement for ghcr.io/huggingface/text-embeddings-inference (amd64 only).
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV FASTEMBED_CACHE_PATH=/data/fastembed
EXPOSE 80
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80"]
