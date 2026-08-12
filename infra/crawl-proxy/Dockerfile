FROM python:3.11-slim-bookworm@sha256:d29f48a31a8b408ed19272ca1e7b10ebae13b240a27e862d3d4217c528e2e0c3

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /app \
    && chown -R appuser:appuser /app

WORKDIR /app
COPY --chown=appuser:appuser server.py /app/server.py

USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/server.py"]
