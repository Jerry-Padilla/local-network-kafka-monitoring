FROM apache/airflow:3.3.2-python3.12

COPY --chown=airflow:root services/analytics /opt/netpulse/services/analytics

RUN python -m pip install --no-cache-dir \
    "apache-airflow==3.3.2" \
    /opt/netpulse/services/analytics
