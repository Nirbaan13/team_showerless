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

# Keep research directories, caches and tests outside the service image.
COPY --chown=app:app ml/service.py ml/detector.py ml/catalogue_db.py ml/smoke_deployment.py ./
COPY --chown=app:app ml/candidate-example.json ml/spherex_3i_atlas.npz ml/spherex-result.png ./
COPY --chown=app:app science/motion/live.py science/motion/prepare_fits.py science/motion/review.py science/motion/detector.py science/motion/ranker.py science/motion/prepared.py science/motion/profiles.py ./science/motion/
COPY --chown=app:app pipeline/unification/ml.py ./pipeline/unification/
COPY --chown=app:app science/motion/cases/december-d2.npz science/motion/cases/december-d6.npz science/motion/cases/vesta-d3.npz science/motion/cases/vesta-d6.npz science/motion/cases/observations.csv science/motion/cases/vesta-horizons.csv ./science/motion/cases/
COPY --chown=app:app ops/ml/compose.yaml ./deploy/compose.yaml

USER app

EXPOSE 8001

HEALTHCHECK --interval=5s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import json, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=2); assert json.load(r)['status'] == 'ok'"

CMD ["uvicorn", "service:app", "--host", "0.0.0.0", "--port", "8001"]
