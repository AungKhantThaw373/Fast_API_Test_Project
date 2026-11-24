import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import async_session, engine
from app.logging_config import configure_app_logging
from app.routes.auth_routes import router as auth_router
from app.routes.bible import router as bible_router
from app.routes.chapters import router as chapter_router
from app.routes.continuity import router as continuity_router
from app.routes.editing_routes import router as editing_router
from app.routes.jobs import router as job_router
from app.routes.stories import router as story_router
from app.routes.system_routes import router as system_router
from app.routes.trash_routes import router as trash_router
from app.routes.user_routes import router as user_router
from app.schema_check import assert_schema_at_head
from app.services.indexing import reconcile_indexing_state, reindex_stale_embedding_models
from app.services.trash import purge_expired_trash

configure_app_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with async_session() as session:
        await assert_schema_at_head(session)
    await reconcile_indexing_state()
    await reindex_stale_embedding_models()
    async with async_session() as session:
        purged = await purge_expired_trash(session)
        await session.commit()
        if purged["stories"] or purged["chapters"]:
            configure_app_logging()
            logging.getLogger("stillroom.api").info(
                "Purged %s expired stories and %s expired chapters from trash",
                purged["stories"],
                purged["chapters"],
            )
    yield
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
app.include_router(chapter_router)
app.include_router(bible_router)
app.include_router(continuity_router)
app.include_router(job_router)
app.include_router(trash_router)
app.include_router(system_router)
app.include_router(editing_router)
