FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY services/query-api /app/services/query-api
RUN python -m pip install --no-cache-dir /app/services/query-api \
    && addgroup --system --gid 10001 netpulse \
    && adduser --system --uid 10001 --ingroup netpulse --home /app netpulse

USER netpulse
CMD ["python", "-m", "netpulse_query_api.entrypoint"]
