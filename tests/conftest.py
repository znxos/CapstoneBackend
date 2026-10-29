import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.session import get_db
from sqlmodel import SQLModel

# Import all models to ensure they are registered with SQLModel.metadata
from app.models.user import User
from app.models.token import VerificationToken, PasswordResetToken
from app.models.event import Event, EventParticipant
from app.models.message import Message
from app.models.rationale import EventRationale

import sqlite3
import json
sqlite3.register_adapter(list, json.dumps)

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import ARRAY

@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "JSON"

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

TestingSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session

app.dependency_overrides[get_db] = override_get_db

from app.api.dependencies import verify_api_key
async def override_verify_api_key():
    return
app.dependency_overrides[verify_api_key] = override_verify_api_key

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
