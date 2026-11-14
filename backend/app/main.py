import os

from fastapi import FastAPI


def create_app() -> FastAPI:
    revision = os.environ.get("APP_REVISION", "development")
    application = FastAPI(title="Space Apps API", version=revision)

    @application.get("/")
    def index() -> dict[str, str]:
        return {"service": "Space Apps API", "version": revision, "docs": "/docs"}

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "revision": revision}

    @application.get("/version")
    def version() -> dict[str, str]:
        return {"version": revision}

    return application


app = create_app()
