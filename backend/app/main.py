from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, posts
from app.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="Social Platform",
        version="0.1.0",
        docs_url="/_internal/docs",
        redoc_url="/_internal/redoc",
        openapi_url="/_internal/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    app.include_router(posts.router)
    return app


app = create_app()