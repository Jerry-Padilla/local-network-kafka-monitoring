FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY packages/contracts /app/packages/contracts
COPY services/simulator /app/services/simulator
RUN python -m pip install --no-cache-dir \
      /app/packages/contracts \
      /app/services/simulator

RUN addgroup --system --gid 10001 netpulse \
    && adduser --system --uid 10001 --ingroup netpulse --home /app netpulse \
    && chown -R netpulse:netpulse /app

USER netpulse

ENTRYPOINT ["python", "-m", "netpulse_simulator"]
CMD ["run", "--scenario", "healthy", "--duration", "30"]
