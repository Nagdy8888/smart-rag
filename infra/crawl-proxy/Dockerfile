FROM python:3.11-slim-trixie@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7 AS builder

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY server.py /app/server.py

FROM gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775

ENV PATH="/usr/local/bin:$PATH" \
    PYTHONPATH="/usr/local/lib/python3.11/site-packages" \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY --from=builder --chown=10001:10001 /usr/local /usr/local
COPY --from=builder --chown=10001:10001 /etc/ssl/certs /etc/ssl/certs
COPY --from=builder --chown=10001:10001 /app /app

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/server.py"]
