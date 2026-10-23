FROM python:3.11-alpine@sha256:6857d2dae63e052057f2db389a7061188ac9a92a3fa8d402bde68f36df6fada1

RUN apk upgrade --no-cache \
    && apk add --no-cache \
        tesseract-ocr \
        tesseract-ocr-data-eng \
        tesseract-ocr-data-ara \
    && adduser -D -u 10001 -s /sbin/nologin parseruser \
    && mkdir -p /app /input /output \
    && chown -R parseruser:parseruser /app /input /output

WORKDIR /app
COPY infra/parser-sandbox/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY infra/parser-sandbox/runner.py /app/runner.py
COPY packages/core/src/smart_rag_core /app/smart_rag_core

USER 10001:10001
ENTRYPOINT []
CMD ["python", "/app/runner.py"]
