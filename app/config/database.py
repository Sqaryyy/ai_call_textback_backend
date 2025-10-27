"""Database configuration and connection setup"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from app.config.settings import get_settings

settings = get_settings()

# Create database engine with connection pooling
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Database dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Drop and recreate all database tables"""
    from app.models.business import Base  # shared Base
    import app.models.user
    import app.models.refresh_token
    import app.models.api_key
    import app.models.api_request_log
    import app.models.email_verification
    import app.models.invite
    import app.models.password_reset
    import app.models.webhook_event
    import app.models.webhook_endpoint
    import app.models.business_knowledge
    import app.models

    print("Dropping existing tables with CASCADE...")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))
        conn.commit()

    print("Creating required extensions...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))
        conn.commit()

    print("Creating all tables...")

    print("Creating required ENUMs...")
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT 1 FROM pg_type WHERE typname = 'invitetype';")
        ).fetchone()
        if not result:
            conn.execute(
                text("CREATE TYPE invitetype AS ENUM ('business', 'platform');")
            )
        conn.commit()

    Base.metadata.create_all(bind=engine)

    print("✅ Database tables created successfully!")


if __name__ == "__main__":
    create_tables()
