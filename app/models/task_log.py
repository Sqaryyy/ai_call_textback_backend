from sqlalchemy import Column, String, DateTime, JSON, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
from .business import Base


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_name = Column(String(100), nullable=False)
    task_id = Column(String(200))  # Celery task ID
    correlation_id = Column(String(100))
    payload = Column(JSON, default=dict)
    status = Column(String(20), nullable=False)  # pending, running, success, failure, retry
    result = Column(JSON, default=dict)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    execution_time_ms = Column(Integer)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
