FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/netpulse

COPY packages/contracts /opt/netpulse/packages/contracts
COPY packages/observability /opt/netpulse/packages/observability
COPY services/event-ingestor /opt/netpulse/services/event-ingestor
COPY services/simulator /opt/netpulse/services/simulator
COPY scripts/seed_airflow_verification.py /opt/netpulse/scripts/seed_airflow_verification.py

RUN python -m pip install --no-cache-dir \
      /opt/netpulse/packages/contracts \
      /opt/netpulse/packages/observability \
      /opt/netpulse/services/event-ingestor \
      /opt/netpulse/services/simulator \
    && python -m pip check \
    && addgroup --system --gid 10001 netpulse \
    && adduser --system --uid 10001 --ingroup netpulse --home /opt/netpulse netpulse \
    && chown -R netpulse:netpulse /opt/netpulse

USER netpulse

ENTRYPOINT ["python", "/opt/netpulse/scripts/seed_airflow_verification.py"]
