from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Index
from gateway.database import Base
from datetime import datetime
import uuid

class RequestLog(Base):
    """SQLAlchemy model for request logs."""
    
    __tablename__ = "request_logs"
    
    id = Column(Integer, primary_key=True)
    request_id = Column(String(36), unique=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    method = Column(String(10), nullable=False)
    path = Column(Text, nullable=False)
    service = Column(String(50), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Float, nullable=False)
    error_message = Column(Text, nullable=True)
    client_ip = Column(String(45), nullable=False)
    retry_count = Column(Integer, default=0)
    circuit_breaker_state = Column(String(20), default="CLOSED")
    
    # Indexes for fast queries
    __table_args__ = (
        Index('idx_request_id', 'request_id'),
        Index('idx_timestamp', 'timestamp'),
        Index('idx_service', 'service'),
    )
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "request_id": self.request_id,
            "timestamp": self.timestamp.isoformat(),
            "method": self.method,
            "path": self.path,
            "service": self.service,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "error_message": self.error_message,
            "client_ip": self.client_ip,
            "retry_count": self.retry_count,
            "circuit_breaker_state": self.circuit_breaker_state,
        }
