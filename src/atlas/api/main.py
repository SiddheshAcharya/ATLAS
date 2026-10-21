"""FastAPI app — all routes under `/api/v1` (docs/API.md).

`uvicorn atlas.api.main:app --reload` for local dev; `make dev` runs this alongside the
Vite frontend. CORS is wide open for local development only — settings.api_cors_origins
narrows it for anything resembling a real deployment.
"""

from __future__ import annotations

from atlas.console_encoding import fix_windows_console_encoding

# Must run before anything logs — sys.stdout/stderr are process-wide, so this also
# covers the asyncio.to_thread worker threads api/tasks.py runs the foraging loop on.
fix_windows_console_encoding()

from pathlib import Path  # noqa: E402

from fastapi import APIRouter, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from atlas import __version__  # noqa: E402
from atlas.api.routes import chat, runs  # noqa: E402
from atlas.api.sse import router as sse_router  # noqa: E402
from atlas.config import settings  # noqa: E402
from atlas.contracts import HealthStatus, ServiceHealth  # noqa: E402
from atlas.health import check_all  # noqa: E402

app = FastAPI(title="ATLAS API", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter(prefix="/api/v1")
v1.include_router(runs.router)
v1.include_router(chat.router)
v1.include_router(sse_router)
app.include_router(v1)


@app.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    rows = check_all()
    services = [ServiceHealth(name=name, ok=ok, detail=detail) for name, ok, detail in rows]
    required_ok = all(ok is not False for name, ok, _ in rows if name == "postgres/sqlite")
    return HealthStatus(services=services, healthy=required_ok)


WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def mount_web(target: FastAPI, dist: Path) -> bool:
    """Serve the built dashboard (`npm run build` -> web/dist) from this same process, so a
    demo is one command and one origin. Registered after every API route, so those win;
    any other path gets index.html and client-side routing takes over."""
    if not (dist / "index.html").is_file():
        return False
    root = dist.resolve()

    @target.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404)
        f = (root / path).resolve()
        if path and f.is_file() and f.is_relative_to(root):
            return FileResponse(f)
        return FileResponse(root / "index.html")

    return True


mount_web(app, WEB_DIST)
