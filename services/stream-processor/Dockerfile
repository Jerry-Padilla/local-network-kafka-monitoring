FROM python:3.12.10-slim-bookworm

ARG SPARK_VERSION=4.1.2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/var/lib/netpulse-streaming \
    PYSPARK_PYTHON=python3 \
    PYSPARK_DRIVER_PYTHON=python3

RUN apt-get update \
    && apt-get install --no-install-recommends -y openjdk-17-jre-headless procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python -m pip install --no-cache-dir "pyspark==${SPARK_VERSION}"

COPY packages/contracts /app/packages/contracts
COPY services/stream-processor /app/services/stream-processor
RUN python -m pip install --no-cache-dir \
      /app/packages/contracts \
      /app/services/stream-processor

RUN addgroup --system --gid 10001 netpulse \
    && adduser --system --uid 10001 --ingroup netpulse \
      --home /var/lib/netpulse-streaming netpulse \
    && mkdir -p \
      /var/lib/netpulse-streaming/checkpoints \
      /var/lib/netpulse-streaming/.ivy2/cache \
      /var/lib/netpulse-streaming/.ivy2/jars \
    && chown -R netpulse:netpulse /app /var/lib/netpulse-streaming

USER netpulse

ENTRYPOINT ["spark-submit"]
CMD ["--master", "local[2]", "--packages", "org.apache.spark:spark-sql-kafka-0-10_2.13:4.1.2", "--conf", "spark.driver.extraJavaOptions=-Divy.cache.dir=/var/lib/netpulse-streaming/.ivy2/cache -Divy.home=/var/lib/netpulse-streaming/.ivy2", "/app/services/stream-processor/app.py"]
