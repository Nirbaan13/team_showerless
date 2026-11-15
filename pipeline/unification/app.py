"""Compose the new private operation with the unchanged team service."""
import os
from pathlib import Path

from service import app
from unification.http import create_router

app.include_router(create_router(Path(os.environ.get("UNIFICATION_DATA_ROOT", "/tmp/spherex_cutouts"))))
