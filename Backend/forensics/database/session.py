"""
TrustAgent — Database Session (Forensics audit_logs)

SQLite cho local/dev; PostgreSQL khi DATABASE_URL trỏ tới Postgres.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    create_async_engine,
    async_sessionmaker,
)

from forensics.config import get_settings, BACKEND_DIR, reset_settings_cache
from forensics.database.models import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _normalize_db_url(db_url: str) -> str:
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if db_url.startswith("sqlite:///") and "+aiosqlite" not in db_url:
        return db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return db_url


def _sqlite_fallback_url() -> str:
    return f"sqlite+aiosqlite:///{(BACKEND_DIR / 'trustagent_forensics.db').as_posix()}"


def _get_engine(force_url: str | None = None) -> AsyncEngine:
    global _engine, _session_factory
    if _engine is None or force_url is not None:
        if force_url is not None:
            if _engine is not None:
                # Caller must dispose old engine first
                pass
            db_url = _normalize_db_url(force_url)
            _session_factory = None
        else:
            db_url = _normalize_db_url(get_settings().database_url)

        connect_args = {}
        if "sqlite" in db_url:
            connect_args = {"check_same_thread": False}

        _engine = create_async_engine(
            db_url,
            echo=False,
            connect_args=connect_args,
        )
        logger.info("[TrustAgent DB] Engine: %s...", db_url[:60])
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _session_factory


async def create_tables() -> None:
    """Tạo bảng audit_logs. Nếu Postgres unreachable → fallback SQLite."""
    global _engine, _session_factory
    try:
        engine = _get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[TrustAgent DB] Bảng audit_logs sẵn sàng")
    except Exception as e:
        logger.warning(
            "[TrustAgent DB] Không kết nối được DB chính (%s). Fallback SQLite.",
            e,
        )
        if _engine is not None:
            await _engine.dispose()
        _engine = None
        _session_factory = None
        # Force sqlite for this process
        os_environ_note = _sqlite_fallback_url()
        reset_settings_cache()
        _get_engine(force_url=os_environ_note)
        engine = _get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("[TrustAgent DB] Fallback SQLite OK: %s", os_environ_note)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session_factory = _get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("[TrustAgent DB] Engine đã đóng")
