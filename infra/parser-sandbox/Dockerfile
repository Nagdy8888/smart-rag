FROM python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        tesseract-ocr-ara \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin parseruser \
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
