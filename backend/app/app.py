from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import engine
from app.logging_config import configure_app_logging
from app.routes.auth_routes import router as auth_router
from app.routes.editing_routes import router as editing_router
from app.routes.story_routes import router as story_router
from app.routes.user_routes import router as user_router
from app.services.indexing import reindex_stale_embedding_models, stop_index_jobs


configure_app_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await reindex_stale_embedding_models()
    yield
    await stop_index_jobs()
    await engine.dispose()


app = FastAPI(
	title="Stillroom",
	description="A chapter writing studio and a structured story draft file library.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(user_router)
app.include_router(story_router)
app.include_router(editing_router)
