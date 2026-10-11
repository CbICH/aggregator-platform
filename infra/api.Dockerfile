FROM python:3.12.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY apps/api/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt && useradd --create-home --uid 10001 signal
COPY --chown=signal:signal apps/api/ ./
USER signal
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
