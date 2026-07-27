import os
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker, Mapped, mapped_column
from sqlalchemy import String, Integer, DateTime
from sqlalchemy.dialects.postgresql import JSONB

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/trustagent_db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class AuditEvent(Base):
    __tablename__ = "audit_events"

    incident_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    tong_hoa_don: Mapped[int] = mapped_column(Integer, default=0)
    tong_loi_thue: Mapped[int] = mapped_column(Integer, default=0)
    z3_status: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(tz=timezone.utc))
    final_audit_log: Mapped[dict] = mapped_column(JSONB, nullable=False)

async def init_db():
    async with engine.begin() as conn:
        # Create table if not exists (dùng trong môi trường test/dev)
        await conn.run_sync(Base.metadata.create_all)
