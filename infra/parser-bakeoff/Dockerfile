FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 10001 parseruser \
    && useradd -u 10001 -g 10001 -M -s /usr/sbin/nologin parseruser \
    && mkdir -p /app /input /output \
    && chown -R parseruser:parseruser /app /input /output

WORKDIR /app
ENV PYTHONPATH=/app
COPY infra/parser-bakeoff/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY infra/parser-bakeoff/runner.py /app/runner.py
COPY packages/core/src/smart_rag_core /app/smart_rag_core

USER 10001:10001
ENTRYPOINT []
CMD ["python", "/app/runner.py"]
