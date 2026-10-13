FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Non-root user. /app/resumes and /app/output are mount points for host folders.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/resumes /app/output \
    && chown -R app:app /app
COPY --chown=app:app . .
USER app

# Hosting platforms (e.g. Render) inject PORT; locally it stays 8000. Always bind all interfaces.
# `exec` keeps uvicorn as PID 1 so it receives SIGTERM and shuts down cleanly.
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.api:app --host 0.0.0.0 --port ${PORT}"]
