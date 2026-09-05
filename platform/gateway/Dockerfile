# Built with platform/ as the context (see docker-compose.yml and platform/.dockerignore) so the
# image carries worker/tenant_keys.py: the gateway must derive exactly the key the worker uses.
FROM python:3.12-slim
WORKDIR /app
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gateway/ .
COPY worker/__init__.py worker/tenant_keys.py ./worker/
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
