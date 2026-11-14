FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home app
COPY --chown=app:app app ./app

ARG APP_REVISION=development
ENV APP_REVISION=${APP_REVISION}
LABEL org.opencontainers.image.revision=${APP_REVISION} \
      org.opencontainers.image.source="https://github.com/Nirbaan13/team_showerless"

USER app
EXPOSE 8000
HEALTHCHECK --interval=3s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import json,os,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=2)); assert d['status']=='ok' and d['revision']==os.environ['APP_REVISION']"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
