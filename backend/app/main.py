from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import get_settings
from .database import init_db
from .kb_integration import get_gateway

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    try:
        get_gateway().initialize()
    except Exception:
        logging.getLogger(__name__).exception("Obsidian 知识库初始化失败，系统继续运行")
    try:
        from .database import get_session_factory
        from .modules.knowledge import sync_all_docs_to_obsidian

        with get_session_factory()() as db:
            sync_all_docs_to_obsidian(db)
    except Exception:
        logging.getLogger(__name__).exception("资料库同步到 Obsidian 目录失败，系统继续运行")
    yield


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="tender-extract + BiaoShu-SKILL + 易标集成流水线",
    lifespan=lifespan,
)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .api import auth, bid_special, kb, kb_files, preprocess, system, tasks, ws  # noqa: E402

app.include_router(auth.router, prefix="/api")
app.include_router(preprocess.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(kb.router, prefix="/api")
app.include_router(kb_files.router, prefix="/api")
app.include_router(bid_special.router, prefix="/api")
app.include_router(system.router, prefix="/api")
app.include_router(ws.router)


def _frontend_dist() -> Path | None:
    """桌面模式下由 FRONTEND_DIST 指定前端构建产物目录。"""
    raw = os.getenv("FRONTEND_DIST", "").strip()
    if not raw:
        return None
    dist = Path(raw)
    return dist if (dist / "index.html").exists() else None


@app.get("/", include_in_schema=False)
def root():
    dist = _frontend_dist()
    if dist is not None:
        return FileResponse(dist / "index.html")
    return {"name": settings.app_name, "version": __version__, "docs": "/docs"}


_dist = _frontend_dist()
if _dist is not None:
    if (_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa_fallback(path: str):
        if path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (_dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(_dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
