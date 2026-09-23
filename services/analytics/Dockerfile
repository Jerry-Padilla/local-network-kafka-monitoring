FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY services/analytics /app/services/analytics
RUN python -m pip install --no-cache-dir /app/services/analytics \
    && addgroup --system --gid 10001 netpulse \
    && adduser --system --uid 10001 --ingroup netpulse --home /app netpulse \
    && chown -R netpulse:netpulse /app

USER netpulse

ENTRYPOINT ["python", "-m", "netpulse_analytics"]
