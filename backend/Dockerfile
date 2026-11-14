FROM eclipse-temurin:25.0.5_8-jdk-noble@sha256:80f67fb3d6f76e2d817d98a4cc2a9cf05f054d4e6adc5e2144bde671d722e63f AS build
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build/backend
COPY backend/sbtw backend/build.sbt ./
COPY backend/project ./project
COPY backend/src ./src
COPY ml/pvusatov/backend/src ../ml/pvusatov/backend/src
RUN ./sbtw stage

FROM eclipse-temurin:25.0.5_8-jre-noble@sha256:e3b6f7887a50f20d8f07abf279d8a81a5953fb398a9555bd9edd56b9bd15968c
RUN apt-get update && apt-get install -y --no-install-recommends curl python3-venv libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --user-group --create-home app \
    && mkdir -p /app/data/tmp && chown -R app:app /app/data
WORKDIR /app
COPY ml/pvusatov/backend/inference/requirements-inference.txt /tmp/inference-requirements.txt
RUN python3 -m venv /opt/inference-venv \
    && /opt/inference-venv/bin/pip install --no-cache-dir --require-hashes -r /tmp/inference-requirements.txt \
    && rm /tmp/inference-requirements.txt
COPY --from=build --chown=app:app /build/backend/target/stage ./
COPY --chown=app:app backend/docs/openai/openapi.yaml ./docs/openai/openapi.yaml
COPY --chown=app:app ml/pvusatov/backend/inference/ml_inference ./inference/ml_inference
COPY --chown=app:app ml/pvusatov/backend/inference/models/ranker.onnx ml/pvusatov/backend/inference/models/metadata.json ./inference/models/
COPY --chown=app:app ml/pvusatov/backend/inference/fixtures ./inference/fixtures
COPY --chown=app:app ml/pvusatov/backend/inference/smoke.py ./inference/smoke.py
ARG APP_REVISION=development
ENV APP_REVISION=${APP_REVISION} \
    DATA_DIR=/app/data \
    ML_ROOT=/app/inference \
    ML_PYTHON=/opt/inference-venv/bin/python \
    PYTHONPATH=/app/inference \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    JAVA_TOOL_OPTIONS="--enable-native-access=ALL-UNNAMED -Xms128m -Xmx2g -Djava.io.tmpdir=/app/data/tmp"
LABEL org.opencontainers.image.revision=${APP_REVISION} \
      org.opencontainers.image.source="https://github.com/Nirbaan13/team_showerless"
VOLUME ["/app/data"]
USER app
EXPOSE 8000 50051
HEALTHCHECK --interval=3s --timeout=3s --start-period=20s --retries=3 \
    CMD curl --fail --silent --max-time 2 http://127.0.0.1:8000/health | grep -Fq "\"revision\":\"$APP_REVISION\""
CMD ["java", "-cp", "classes:lib/*", "spaceapps.bootstrap.Main"]
