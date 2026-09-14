"""FastAPI 入口：路由装配、静态资源、生命周期初始化。"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import BASE_DIR, DATA_DIR, ensure_dirs
from .core.engine.web_collector import web_collector
from .database import init_db
from .api import (
    attachments,
    domains,
    hits,
    platforms,
    results,
    rules,
    settings,
    syntax_dicts,
    tasks,
    ws,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    init_db()
    yield
    await web_collector.aclose()


app = FastAPI(
    title="多平台敏感信息检索系统",
    version="1.0.0",
    lifespan=lifespan,
)

# 本地开发：Vite dev server 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"
for module in (
    platforms,
    tasks,
    results,
    hits,
    rules,
    syntax_dicts,
    attachments,
    domains,
    settings,
):
    app.include_router(module.router, prefix=API_PREFIX)

app.include_router(ws.router)

# 截图静态服务：/screenshots/<相对 data 的路径>，目录被限制在 data/ 内
app.mount("/screenshots", StaticFiles(directory=str(DATA_DIR)), name="screenshots")


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 生产便捷模式：前端已构建时由后端单端口托管（开发期走 Vite 5173 代理）
_DIST_DIR = BASE_DIR / "frontend" / "dist"
if _DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST_DIR / "assets")), name="assets")

    @app.exception_handler(404)
    async def spa_fallback(request: Request, exc):
        # API/WS/静态资源保持 404，其余路径回退 index.html（vue-router history 模式）
        path = request.url.path
        if path.startswith(("/api/", "/ws/", "/screenshots/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        index_file = _DIST_DIR / "index.html"
        if request.method == "GET" and index_file.exists():
            return FileResponse(index_file)
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    @app.get("/")
    def index():
        return FileResponse(_DIST_DIR / "index.html")
