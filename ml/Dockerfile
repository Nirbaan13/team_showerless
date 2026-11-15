FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY ml/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ARG APP_REVISION=unknown
ENV APP_REVISION=${APP_REVISION} \
    XDG_CACHE_HOME=/tmp/cache
LABEL org.opencontainers.image.revision=${APP_REVISION}

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/data \
    && chown app:app /app/data

COPY --chown=app:app ml/ ./
COPY --chown=app:app science/motion/ ./science/motion/
COPY --chown=app:app ops/ml/compose.yaml ./deploy/compose.yaml

USER app

EXPOSE 8001

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import json, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2); assert json.load(r)['status'] == 'ok'"

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
