from fastapi import FastAPI
from app.db import create_db_and_tables
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.routes.rooms_route import router as rooms_router
from app.routes.auth_routes import router as auth_router
from app.routes.docs_routes import router as docs_router
from app.routes.user_routes import router as user_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code: Create database and tables
    await create_db_and_tables()
    yield
    # Shutdown code (if needed) can be added here

app = FastAPI(lifespan=lifespan,root_path="/api/py")

# CORS configuration to allow requests from the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # your Next.js frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rooms_router)
app.include_router(auth_router)
app.include_router(docs_router)
app.include_router(user_router)