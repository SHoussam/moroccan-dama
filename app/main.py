import logging
import os
from pathlib import Path
import re

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.rooms import router as rooms_router
from app.game.config import DEFAULT_RULES_CONFIG, RulesConfig
from app.realtime.websocket import ConnectionHub, router as ws_router
from app.rooms.manager import RoomError, RoomManager

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"
_TOKEN_QUERY_RE = re.compile(r"(token=)[^&\s\"']+", re.IGNORECASE)


class TokenRedactingFilter(logging.Filter):
    """Redacts `token=...` query parameters from Uvicorn and application log records."""

    @staticmethod
    def _scrub(value: object) -> object:
        if isinstance(value, str) and "token=" in value.lower():
            return _TOKEN_QUERY_RE.sub(r"\1[REDACTED]", value)
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _TOKEN_QUERY_RE.sub(r"\1[REDACTED]", record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(self._scrub(a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: self._scrub(v) for k, v in record.args.items()}
        return True


def _install_log_redaction() -> None:
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(logger_name)
        if not any(isinstance(f, TokenRedactingFilter) for f in lg.filters):
            lg.addFilter(TokenRedactingFilter())


def _parse_origins(app_env: str, raw_origins: str, public_base_url: str) -> list[str]:
    items = [o.strip() for o in raw_origins.split(",") if o.strip()]
    if items:
        return items
    if app_env.lower() == "production" and public_base_url:
        return [public_base_url.rstrip("/")]
    return ["http://127.0.0.1:8000", "http://localhost:8000"]


def create_app(
    *,
    room_manager: RoomManager | None = None,
    rules_config: RulesConfig = DEFAULT_RULES_CONFIG,
) -> FastAPI:
    _install_log_redaction()
    app_env = os.getenv("APP_ENV", "development")
    public_base_url = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    allowed_origins = _parse_origins(
        app_env, os.getenv("ALLOWED_ORIGINS", ""), public_base_url
    )

    if room_manager is None:
        room_manager = RoomManager(
            room_code_length=int(os.getenv("ROOM_CODE_LENGTH", "6")),
            waiting_room_ttl_seconds=int(os.getenv("WAITING_ROOM_TTL_SECONDS", "1800")),
            disconnect_grace_seconds=int(os.getenv("DISCONNECT_GRACE_SECONDS", "120")),
            finished_room_ttl_seconds=int(os.getenv("FINISHED_ROOM_TTL_SECONDS", "1800")),
            rules_config=rules_config,
        )

    application = FastAPI(
        title="Moroccan Dama — Private Online Multiplayer",
        version="1.0.0",
        docs_url="/api/docs" if app_env != "production" else None,
        redoc_url=None,
    )

    application.state.room_manager = room_manager
    application.state.connection_hub = ConnectionHub()
    application.state.max_ws_message_bytes = int(
        os.getenv("MAX_WS_MESSAGE_BYTES", "4096")
    )
    application.state.ws_rate_limit_per_second = int(
        os.getenv("WS_RATE_LIMIT_PER_SECOND", "15")
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Player-Token"],
    )

    @application.exception_handler(RoomError)
    async def handle_room_error(_request: Request, exc: RoomError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected server error occurred.",
                }
            },
        )

    @application.get("/healthz", tags=["health"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    application.include_router(rooms_router)
    application.include_router(ws_router)

    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @application.get("/", include_in_schema=False)
    async def serve_home() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/game/{room_code}", include_in_schema=False)
    async def serve_game_route(room_code: str) -> FileResponse:
        _ = room_code
        return FileResponse(STATIC_DIR / "index.html")

    return application


app = create_app()
