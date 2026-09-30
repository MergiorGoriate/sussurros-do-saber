FROM node:22-bookworm-slim AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tailwind.config.js ./
COPY static ./static
COPY templates ./templates
RUN npm run build:css

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000
WORKDIR /app
COPY requirements.txt ./
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --shell /usr/sbin/nologin appuser
COPY . .
COPY --from=assets /app/static/css/tailwind.css ./static/css/tailwind.css
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 CMD curl --fail --silent http://127.0.0.1:${PORT}/healthz || exit 1
CMD ["sh", "-c", "exec python -m gunicorn app:app --bind 0.0.0.0:${PORT} --workers 1 --timeout 120 --access-logfile - --error-logfile - --capture-output --log-level info"]
