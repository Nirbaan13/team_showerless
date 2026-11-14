FROM eclipse-temurin:25.0.5_8-jdk-noble@sha256:80f67fb3d6f76e2d817d98a4cc2a9cf05f054d4e6adc5e2144bde671d722e63f AS build
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY backend/sbtw backend/build.sbt ./
COPY backend/project ./project
COPY backend/src ./src
RUN ./sbtw stage

FROM eclipse-temurin:25.0.5_8-jre-noble@sha256:e3b6f7887a50f20d8f07abf279d8a81a5953fb398a9555bd9edd56b9bd15968c
COPY backend/processing/requirements-processing.txt /tmp/requirements-processing.txt
RUN apt-get update && apt-get install -y --no-install-recommends curl python3 python3-venv \
    && python3 -m venv /opt/inference-venv \
    && /opt/inference-venv/bin/pip install --no-cache-dir --only-binary=:all: --require-hashes -r /tmp/requirements-processing.txt \
    && rm /tmp/requirements-processing.txt \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --user-group --create-home app \
    && mkdir -p /app/data/tmp && chown -R app:app /app/data
WORKDIR /app
COPY --from=build --chown=app:app /build/target/stage ./
COPY --chown=app:app backend/docs/openai/openapi.yaml ./docs/openai/openapi.yaml
COPY --chown=app:app backend/processing/worker.py ./processing/worker.py
COPY --chown=app:app pipeline/spherex/cleaning.py ./pipeline/spherex/cleaning.py
ARG APP_REVISION=development
ENV APP_REVISION=${APP_REVISION} \
    DATA_DIR=/app/data \
    PROCESSING_PYTHON=/opt/inference-venv/bin/python \
    PROCESSING_WORKER=/app/processing/worker.py \
    PIPELINE_ROOT=/app/pipeline \
    JAVA_TOOL_OPTIONS="--enable-native-access=ALL-UNNAMED -Xms128m -Xmx2g -Djava.io.tmpdir=/app/data/tmp"
LABEL org.opencontainers.image.revision=${APP_REVISION} \
      org.opencontainers.image.source="https://github.com/Nirbaan13/team_showerless"
VOLUME ["/app/data"]
USER app
EXPOSE 8000 50051
HEALTHCHECK --interval=3s --timeout=3s --start-period=20s --retries=3 \
    CMD curl --fail --silent --max-time 2 http://127.0.0.1:8000/health | grep -Fq "\"revision\":\"$APP_REVISION\""
CMD ["java", "-cp", "classes:lib/*", "spaceapps.bootstrap.Main"]
