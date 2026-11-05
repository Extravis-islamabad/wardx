# WardX backend: API, scheduler and SSH session gateway share this image;
# WARDX_APP_ROLE picks which one a container runs (see docker-compose.yml).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 wardx \
 && useradd --system --uid 10001 --gid wardx --home-dir /app --shell /usr/sbin/nologin wardx

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=wardx:wardx main.py ./
COPY --chown=wardx:wardx src ./src
COPY --chown=wardx:wardx migrations ./migrations
COPY --chown=wardx:wardx docker/entrypoint.sh /usr/local/bin/wardx-entrypoint

# /data holds recordings and the gateway host key; mount a volume there.
RUN chmod 0755 /usr/local/bin/wardx-entrypoint \
 && mkdir -p /data/recordings /data/keys \
 && chown -R wardx:wardx /data && chmod 0700 /data/keys

ENV WARDX_ENVIRONMENT=production \
    WARDX_APP_ROLE=api \
    WARDX_RECORDING_DIR=/data/recordings \
    WARDX_API_PORT=8741

USER wardx
VOLUME ["/data"]
EXPOSE 8741 2222

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD ["python", "-c", "import os,socket,sys,urllib.request as u; r=os.environ.get('WARDX_APP_ROLE','api'); p=os.environ.get('WARDX_API_PORT','8741'); g=int(os.environ.get('WARDX_GATEWAY_PORT','2222')); sys.exit(0) if r=='scheduler' else (socket.create_connection(('127.0.0.1',g),3).close() if r=='gateway' else u.urlopen(f'http://127.0.0.1:{p}/health',timeout=3))"]

ENTRYPOINT ["wardx-entrypoint"]
CMD ["python", "main.py"]
