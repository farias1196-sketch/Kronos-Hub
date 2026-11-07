from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func


DATA_DIR = Path(__file__).resolve().parents[2] / ".local"
DATA_DIR.mkdir(exist_ok=True)

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATA_DIR / 'chronos_adm.db'}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SuperAdmin(Base):
    __tablename__ = "super_admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False, default="Administrador")
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AdmCompany(Base):
    __tablename__ = "adm_companies"

    id = Column(Integer, primary_key=True, index=True)
    tenant_slug = Column(String, unique=True, nullable=False, index=True)
    tenant_name = Column(String, nullable=False)
    owner_name = Column(String, default="")
    owner_email = Column(String, default="")
    status = Column(String, default="TRIAL")
    plan_slug = Column(String, default="trial")
    ai_weekly_limit = Column(Integer, default=0)
    ai_monthly_limit = Column(Integer, default=0)
    notes = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AdmModule(Base):
    __tablename__ = "adm_modules"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    port = Column(Integer, nullable=True)
    status = Column(String, default="pending")
    visible = Column(Boolean, default=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AiPlan(Base):
    __tablename__ = "ai_plans"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    monthly_price = Column(Float, default=0)
    weekly_credits = Column(Integer, default=0)
    monthly_credits = Column(Integer, default=0)
    active = Column(Boolean, default=True)
    description = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GlobalNotice(Base):
    __tablename__ = "global_notices"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, default="Aviso global")
    message = Column(Text, nullable=False)
    tone = Column(String, default="info")
    active = Column(Boolean, default=True)
    dismissible = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AdmSetting(Base):
    __tablename__ = "adm_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text, default="")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
