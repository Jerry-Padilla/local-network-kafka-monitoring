FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY packages/contracts /app/packages/contracts
COPY services/event-ingestor /app/services/event-ingestor
RUN python -m pip install --no-cache-dir \
      /app/packages/contracts \
      /app/services/event-ingestor

COPY database /app/database

RUN addgroup --system --gid 10001 netpulse \
    && adduser --system --uid 10001 --ingroup netpulse --home /app netpulse \
    && chown -R netpulse:netpulse /app

USER netpulse

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
  CMD ["python", "-m", "netpulse_ingestion", "healthcheck"]

ENTRYPOINT ["python", "-m", "netpulse_ingestion"]
CMD ["run"]
