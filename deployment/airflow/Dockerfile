FROM apache/airflow:3.3.2-python3.12

COPY --chown=airflow:root services/analytics /opt/netpulse/services/analytics
COPY --chown=airflow:root scripts/wait_for_airflow_source.py scripts/verify_airflow.py /opt/netpulse/scripts/

RUN python -m pip install --no-cache-dir \
    "apache-airflow==3.3.2" \
    /opt/netpulse/services/analytics \
    && python -m pip check
