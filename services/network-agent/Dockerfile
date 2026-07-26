FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y iputils-ping iw \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY packages/contracts /app/packages/contracts
COPY services/network-agent /app/services/network-agent
RUN python -m pip install --no-cache-dir \
      /app/packages/contracts \
      /app/services/network-agent

RUN addgroup --system --gid 10001 netpulse \
    && adduser --system --uid 10001 --ingroup netpulse --home /app netpulse \
    && mkdir -p /var/lib/netpulse-agent \
    && chown -R netpulse:netpulse /app /var/lib/netpulse-agent

USER netpulse

ENTRYPOINT ["python", "-m", "netpulse_agent"]
CMD ["--config", "/etc/netpulse-agent/agent.yaml", "run"]
