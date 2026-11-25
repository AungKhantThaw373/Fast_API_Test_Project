import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.db import async_session, engine
from app.logging_config import configure_app_logging
from app.middleware import RequestContextMiddleware
from app.routes.account_routes import router as account_router
from app.routes.ai_usage import router as ai_usage_router
from app.routes.arcs import arc_router
from app.routes.arcs import router as story_arc_router
from app.routes.ask import router as ask_router
from app.routes.auth_routes import router as auth_router
from app.routes.bible import router as bible_router
from app.routes.chapters import router as chapter_router
from app.routes.continuity import router as continuity_router
from app.routes.editing_routes import router as editing_router
from app.routes.entities import router as entities_router
from app.routes.export_routes import router as export_router
from app.routes.health import router as health_router
from app.routes.jobs import router as job_router
from app.routes.recaps import router as recap_router
from app.routes.search import router as search_router
from app.routes.stories import router as story_router
from app.routes.system_routes import router as system_router
from app.routes.trash_routes import router as trash_router
from app.routes.user_routes import router as user_router
from app.routes.wiki import router as wiki_router
from app.schema_check import assert_schema_at_head
from app.security_headers import SecurityHeadersMiddleware
from app.security_middleware import SecurityMiddleware
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
    allow_origins=settings.frontend_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Every error body carries the request id the writer can quote."""
    from app.middleware import current_request_id

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": current_request_id()},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    from app.middleware import current_request_id

    # ``errors()`` can carry exception objects in ``ctx`` (model validators raise
    # ValueError), which JSON cannot encode. Keep the message and drop the rest.
    detail = [
        {
            "type": error.get("type"),
            "loc": list(error.get("loc", ())),
            "msg": error.get("msg"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": detail, "request_id": current_request_id()},
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    from app.middleware import current_request_id

    logging.getLogger("stillroom.api").exception("Unhandled error on %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Something went wrong. Quote the request id when reporting it.",
            "request_id": current_request_id(),
        },
    )


app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(account_router)
app.include_router(story_router)
app.include_router(ai_usage_router)
app.include_router(ask_router)
app.include_router(story_arc_router)
app.include_router(arc_router)
app.include_router(chapter_router)
app.include_router(bible_router)
app.include_router(continuity_router)
app.include_router(job_router)
app.include_router(trash_router)
app.include_router(system_router)
app.include_router(editing_router)
app.include_router(entities_router)
app.include_router(wiki_router)
app.include_router(search_router)
app.include_router(recap_router)
app.include_router(export_router)
