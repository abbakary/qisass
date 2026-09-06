from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import settings
from .database import DATA_DIR, Base, engine, SessionLocal, migrate_schema
from .routes import router
from .seed import seed_if_empty


class MediaCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/media/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
            response.headers.setdefault("Accept-Ranges", "bytes")
        return response


app = FastAPI(title="Qisas API", version="1.0.0")
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(MediaCacheMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_origin_regex=r"https://.*\.(vercel\.app|railway\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads = DATA_DIR / "uploads"
uploads.mkdir(parents=True, exist_ok=True)
app.mount("/media/uploads", StaticFiles(directory=str(uploads)), name="uploads")
app.include_router(router, prefix="/api")


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    db = SessionLocal()
    try:
        seed_if_empty(db)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "qisas-api"}
