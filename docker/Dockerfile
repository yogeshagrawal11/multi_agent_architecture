# Author: Yogesh Agrawal
# Single-image build: FastAPI + MCP servers + mock bank + Presidio +
# Langfuse v2 server + Postgres + Nginx, all run by supervisord.
#
# NOTE: This is a demo/learning deployment. In production these would be
# separate services. We intentionally pack them into one container because
# the project requires a single container.

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    DATA_DIR=/data

# ---- System packages: nginx, supervisor, tls tooling ----
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx \
        supervisor \
        openssl \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

# ---- Python deps (cached layer) ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

# ---- Observability note ----
# The app uses the Langfuse SDK (installed via requirements.txt) and is a safe
# no-op when LANGFUSE_ENABLED=false (the default). The Langfuse *server* is a
# separate Docker image (langfuse/langfuse:2) and is intentionally NOT bundled
# into this single container. To enable tracing, run Langfuse separately and set
# LANGFUSE_ENABLED=true + LANGFUSE_HOST/keys in .env.

# ---- App source ----
COPY . .

# ---- Self-signed TLS cert for the demo edge ----
RUN mkdir -p /etc/nginx/certs \
    && openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
        -keyout /etc/nginx/certs/server.key \
        -out /etc/nginx/certs/server.crt \
        -subj "/CN=localhost" \
    && mkdir -p "$DATA_DIR"

# ---- Edge + process manager config ----
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisor/conf.d/app.conf
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8080 8443

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
