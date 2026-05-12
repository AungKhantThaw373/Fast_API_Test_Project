from fastapi import FastAPI
from app.db import create_db_and_tables
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from backend.app.routes.rooms_route import router
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

app.include_router(router)