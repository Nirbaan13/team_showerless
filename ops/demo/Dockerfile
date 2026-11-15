# Build context is an extracted bundle. Supply --build-arg BUNDLE_FILE=... only
# when its verified outer archive has a different name in the build context.
# CLI uses the mounted host socket; this image never starts a Docker daemon.
ARG DOCKER_CLI_IMAGE=docker:28.5.2-cli@sha256:625d9431a9f54c5a2bc90f24f0e1c3d55b1349fd857dd85035f98c2c9acbdd4d
FROM ${DOCKER_CLI_IMAGE}
RUN apk add --no-cache python3
WORKDIR /opt/spaceapps-demo
ARG BUNDLE_FILE=bundle.tar.gz
COPY bundle.py /usr/local/lib/spaceapps-demo/bundle.py
COPY ${BUNDLE_FILE} /opt/spaceapps-demo/bundle.tar.gz
ENTRYPOINT ["python3", "/usr/local/lib/spaceapps-demo/bundle.py", "install", "--bundle", "/opt/spaceapps-demo/bundle.tar.gz", "--engine", "docker"]
