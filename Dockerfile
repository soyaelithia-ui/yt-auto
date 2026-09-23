FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    BOT_HOME=/home/appuser \
    HOME=/home/appuser \
    ANTIGRAVITY_CLI_HOME=/home/appuser/.gemini \
    ANTIGRAVITY_AGENTS_APP_DATA_DIR=/home/appuser/.gemini/antigravity-cli \
    AGY_BIN=/usr/local/bin/agy \
    WORK_ROOT=/app/work \
    ARTIFACT_ROOT=/app/artifacts \
    YOUTUBE_AUTOMATION_DB=/app/data/shorts_queue.db

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      ffmpeg \
      fonts-dejavu-core \
      libass-dev \
      libx264-dev \
      tini \
      libnss3 \
      libnspr4 \
      libatk1.0-0 \
      libatk-bridge2.0-0 \
      libcups2 \
      libdrm2 \
      libxkbcommon0 \
      libxcomposite1 \
      libxdamage1 \
      libxfixes3 \
      libxrandr2 \
      libgbm1 \
      libasound2 \
      libxshmfence1 \
      libegl1 \
      libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt constraints.txt /app/
COPY scripts/docker_entrypoint.sh /entrypoint.sh
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && playwright install chromium \
    && (curl -fsSL https://antigravity.google/cli/install.sh | bash 2>/dev/null || true) \
    && (cp -f /root/.local/bin/agy /usr/local/bin/agy 2>/dev/null || true) \
    && chmod +x /entrypoint.sh \
    && ([ -f /usr/local/bin/agy ] && chmod 755 /usr/local/bin/agy || true) \
    && mkdir -p /app/data /app/work /app/artifacts /app/logs /app/output \
         /home/appuser/.gemini/antigravity-cli \
    && groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --home-dir /home/appuser --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /home/appuser /ms-playwright \
         /app/data /app/work /app/artifacts /app/logs /app/output
COPY . /app
RUN rm -rf /app/build /app/.venv && chown -R appuser:appuser /app

USER 10001:10001

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD ["python", "healthcheck.py"]

ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
CMD ["python", "main.py", "daemon", "--channel", "all", "--interval", "60"]
