# app/config/database.py - FIXED
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

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Database dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Create all database tables"""
    # Import all models to register them
    from app.models.business import Base as BusinessBase
    from app.models.business_knowledge import Base as KnowledgeBase

    print("Dropping all tables with CASCADE...")

    # Use raw SQL to drop with CASCADE
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS business_knowledge CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS business_hours CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS businesses CASCADE"))
        conn.execute(text("DROP TYPE IF EXISTS knowledge_category CASCADE"))
        conn.commit()

    print("Creating pgvector extension...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    print("Creating knowledge_category enum...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TYPE knowledge_category AS ENUM (
                'service_info',
                'pricing',
                'policies',
                'faq',
                'business_hours',
                'contact_info',
                'general'
            )
        """))
        conn.commit()

    print("Creating all tables...")
    BusinessBase.metadata.create_all(bind=engine)
    KnowledgeBase.metadata.create_all(bind=engine)

    print("Creating vector indexes...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_business_knowledge_embedding 
            ON business_knowledge 
            USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = 100)
        """))
        conn.commit()

    print("✅ Database tables created successfully!")


if __name__ == "__main__":
    create_tables()