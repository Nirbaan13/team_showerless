"""Private, bounded transport for the image-unification numerical worker."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

MAX_REQUEST_BYTES = 131072
MAX_RESPONSE_BYTES = 65536


class WorkerFailure(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _identifier(value: object) -> str:
    try:
        if not isinstance(value, str) or str(UUID(value)) != value:
            raise ValueError
        return value
    except (ValueError, TypeError, AttributeError):
        raise WorkerFailure(422, "invalid_request", "job_id must be a canonical UUID") from None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Repeated property")
        result[key] = value
    return result


def _json(data: bytes):
    return json.loads(data, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


class Supervisor:
    """One numerical child per pipeline process; cleanup always precedes lease release."""
    def __init__(self, root: Path, deadline: float = 120):
        self.root = root.resolve()
        self.deadline = deadline
        self.busy = False

    def _directory(self, job_id: str) -> Path:
        path = self.root
        for name in ("unifications", job_id):
            path = path / name
            if path.is_symlink():
                raise WorkerFailure(422, "invalid_request", "Invalid job directory")
            path.mkdir(exist_ok=True)
            if not path.is_dir():
                raise WorkerFailure(422, "invalid_request", "Invalid job directory")
        return path

    async def run(self, payload: dict, disconnected: Callable[[], Awaitable[bool]] | None = None) -> dict:
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise WorkerFailure(422, "invalid_request", "Expected schema_version 1 object")
        job_id = _identifier(payload.get("job_id"))
        if self.busy:
            raise WorkerFailure(429, "pipeline_busy", "An image unification is already running")
        self.busy = True
        request_path = None
        spawn = None
        tasks = []
        succeeded = False
        try:
            directory = self._directory(job_id)
            if (directory / "output").exists():
                raise WorkerFailure(409, "job_exists", "This job already has an output")
            candidate = directory / "request.json"
            encoded = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode()
            if len(encoded) > MAX_REQUEST_BYTES:
                raise WorkerFailure(413, "invalid_request", "Request exceeds 128 KiB")
            try:
                fd = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                raise WorkerFailure(409, "job_exists", "This job is already admitted") from None
            request_path = candidate
            with os.fdopen(fd, "wb") as stream:
                stream.write(encoded)
            environment = dict(os.environ, UNIFICATION_DATA_ROOT=str(self.root),
                               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                sys.executable, "-m", "unification.worker", str(request_path),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=environment))

            async def read_result():
                child = await asyncio.shield(spawn)
                data = bytearray()
                while chunk := await child.stdout.read(8192):
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise WorkerFailure(502, "pipeline_protocol", "Worker response exceeds its byte budget")
                status = await child.wait()
                try:
                    result = _json(data)
                except (ValueError, UnicodeError):
                    raise WorkerFailure(502, "pipeline_protocol", "Worker did not return valid JSON") from None
                if status != 0:
                    raise WorkerFailure(422, "unification_failed", "Image decoding or scientific validation failed")
                if not isinstance(result, dict) or result.get("schema_version") != 1 or result.get("job_id") != job_id or result.get("status") != "completed":
                    raise WorkerFailure(502, "pipeline_protocol", "Worker returned an inconsistent job result")
                return result

            async def watch_disconnect():
                while True:
                    if disconnected is not None and await disconnected():
                        raise WorkerFailure(499, "client_disconnected", "The requesting client disconnected")
                    await asyncio.sleep(0.05)

            result_task = asyncio.create_task(read_result())
            disconnected_task = asyncio.create_task(watch_disconnect())
            tasks = [result_task, disconnected_task]
            done, _ = await asyncio.wait(tasks, timeout=self.deadline, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise WorkerFailure(504, "pipeline_timeout", "Image unification exceeded its time budget")
            # A simultaneous disconnect wins; no completed result is published to a lost client.
            if disconnected_task in done:
                await disconnected_task
            result = await result_task
            succeeded = True
            return result
        finally:
            async def cleanup():
                try:
                    if spawn is not None:
                        child = await spawn
                        if child.returncode is None:
                            try:
                                child.kill()
                            except ProcessLookupError:
                                pass
                        await child.wait()
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    if request_path is not None:
                        request_path.unlink(missing_ok=True)
                        if not succeeded:
                            output = request_path.parent / "output"
                            if output.is_dir() and not output.is_symlink():
                                shutil.rmtree(output)
            cleanup_task = asyncio.create_task(cleanup())
            try:
                # Shield spawning too: cancellation can arrive after the OS child exists
                # but before create_subprocess_exec hands us its Process handle.
                while not cleanup_task.done():
                    try:
                        await asyncio.shield(cleanup_task)
                    except asyncio.CancelledError:
                        continue
                cleanup_task.result()
            finally:
                self.busy = False


def create_router(root: Path, deadline: float = 120) -> APIRouter:
    supervisor = Supervisor(root, deadline)
    router = APIRouter()

    @router.post("/internal/image-unifications")
    async def unify(request: Request):
        try:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > MAX_REQUEST_BYTES:
                    raise WorkerFailure(413, "invalid_request", "Request exceeds 128 KiB")
            try:
                payload = _json(body)
            except (ValueError, UnicodeError):
                raise WorkerFailure(422, "invalid_request", "Expected a JSON object with unique properties") from None
            return await supervisor.run(payload, request.is_disconnected)
        except WorkerFailure as error:
            return JSONResponse({"code": error.code, "message": error.message}, status_code=error.status)
        except (ValueError, OSError):
            return JSONResponse({"code": "pipeline_unavailable", "message": "The pipeline cannot access its job storage"}, status_code=503)

    return router
