FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 8443

CMD ["python", "-m", "osk", "start", "default"]
