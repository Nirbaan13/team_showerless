FROM nginx:stable-alpine@sha256:901e593c95dc85f5a729f5765516321366ef4ac401821431d408897e95287d0a
ARG APP_REVISION
ENV FRONTEND_REVISION=${APP_REVISION}
LABEL org.opencontainers.image.revision=${APP_REVISION}
COPY ops/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/dist/ /usr/share/nginx/html/
RUN test -n "$FRONTEND_REVISION" && printf '{"version":"%s"}\n' "$FRONTEND_REVISION" > /usr/share/nginx/html/frontend-version.json
HEALTHCHECK --interval=3s --timeout=2s --start-period=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/frontend-version.json | grep -Fq "\"$FRONTEND_REVISION\"" && wget -qO- http://127.0.0.1:8080/ | grep -q 'id="root"'
EXPOSE 8080
