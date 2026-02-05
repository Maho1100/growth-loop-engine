from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import create_pool, close_pool
from app.routers import events, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield
    await close_pool()


app = FastAPI(
    title="Growth Loop Engine API",
    version="0.1.0",
    description="学習継続を支えるための行動ログ基盤（MVP）。",
    lifespan=lifespan,
)

app.include_router(events.router, prefix="/v1", tags=["Events"])
app.include_router(users.router, prefix="/v1", tags=["Users"])
