FROM python:3.12-slim

LABEL org.opencontainers.image.title="The Big Tree Roster"
LABEL org.opencontainers.image.description="Private invite-only roster and round engine for GamePoint-style card-game evenings"
LABEL org.opencontainers.image.source="https://github.com/thebigtree/roster.thebigtree.life"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8500 \
    ROSTER_DATA_DIR=/data \
    ROSTER_HOSTNAME=roster.thebigtree.life

WORKDIR /app
COPY app/ /app/

RUN useradd --system --uid 10001 --home /app roster \
    && mkdir -p /data \
    && chown -R roster:roster /app /data

USER roster
VOLUME ["/data"]
EXPOSE 8500

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8500/healthz', timeout=2).read()"

CMD ["python", "/app/server.py"]
