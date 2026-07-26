FROM python:3.12.10-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /workspace
COPY . /workspace
RUN python -m pip install --no-cache-dir -r requirements-dev.txt

ENTRYPOINT ["python", "-m", "pytest"]
