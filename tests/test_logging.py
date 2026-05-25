import pytest
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from gateway.models import RequestLog, Base
from gateway.database import DATABASE_URL


# ============================================================================
# DAY 7: Logging + Monitoring Tests
# ============================================================================

# Use test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://gateway:gateway_password@localhost:5432/gateway_logs_test"
)

# Check if database is available
def is_postgres_available():
    """Check if PostgreSQL is available by trying to connect."""
    try:
        engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, connect_args={"timeout": 2})
        with engine.connect() as conn:
            return True
    except Exception:
        return False

# Mark all tests in this module as skipped if Postgres is not available
pytestmark = pytest.mark.skipif(
    not is_postgres_available(),
    reason="PostgreSQL not available - start with: docker-compose up postgres"
)


@pytest.fixture(scope="function")
def test_db():
    """Create test database and clean up after tests."""
    # Create test engine
    engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    # Create session
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = TestSessionLocal()
    
    yield db
    
    # Cleanup
    db.close()
    Base.metadata.drop_all(bind=engine)


class TestRequestLogModel:
    """Test RequestLog model."""
    
    def test_request_log_creation(self, test_db):
        """Test creating a request log entry."""
        log = RequestLog(
            request_id="123e4567-e89b-12d3-a456-426614174000",
            method="GET",
            path="/api/users",
            service="auth",
            status_code=200,
            response_time_ms=45.2,
            client_ip="192.168.1.1",
            retry_count=0,
            circuit_breaker_state="CLOSED"
        )
        
        test_db.add(log)
        test_db.commit()
        
        assert log.id is not None
        assert log.request_id == "123e4567-e89b-12d3-a456-426614174000"
        assert log.method == "GET"
        assert log.service == "auth"
        assert log.status_code == 200
    
    def test_request_log_to_dict(self, test_db):
        """Test converting request log to dictionary."""
        log = RequestLog(
            request_id="123e4567-e89b-12d3-a456-426614174000",
            method="POST",
            path="/api/auth/login",
            service="auth",
            status_code=201,
            response_time_ms=120.5,
            client_ip="192.168.1.100",
            error_message=None,
            retry_count=1,
            circuit_breaker_state="CLOSED"
        )
        
        test_db.add(log)
        test_db.commit()
        
        log_dict = log.to_dict()
        
        assert log_dict["request_id"] == "123e4567-e89b-12d3-a456-426614174000"
        assert log_dict["method"] == "POST"
        assert log_dict["status_code"] == 201
        assert log_dict["response_time_ms"] == 120.5
        assert log_dict["retry_count"] == 1
        assert log_dict["circuit_breaker_state"] == "CLOSED"
    
    def test_request_log_with_error(self, test_db):
        """Test logging requests with errors."""
        log = RequestLog(
            request_id="223e4567-e89b-12d3-a456-426614174000",
            method="GET",
            path="/api/users/999",
            service="auth",
            status_code=404,
            response_time_ms=15.3,
            client_ip="192.168.1.50",
            error_message="User not found",
            retry_count=0,
            circuit_breaker_state="CLOSED"
        )
        
        test_db.add(log)
        test_db.commit()
        
        assert log.status_code == 404
        assert log.error_message == "User not found"


class TestLogQueries:
    """Test various query patterns against logs."""
    
    def test_query_by_service(self, test_db):
        """Test filtering logs by service."""
        # Add test data
        for i in range(3):
            log = RequestLog(
                request_id=f"123e4567-e89b-12d3-a456-42661417400{i}",
                method="GET",
                path=f"/api/users/{i}",
                service="auth" if i < 2 else "chat",
                status_code=200,
                response_time_ms=50.0,
                client_ip="192.168.1.1",
                retry_count=0,
                circuit_breaker_state="CLOSED"
            )
            test_db.add(log)
        
        test_db.commit()
        
        # Query by service
        auth_logs = test_db.query(RequestLog).filter(RequestLog.service == "auth").all()
        assert len(auth_logs) == 2
        
        chat_logs = test_db.query(RequestLog).filter(RequestLog.service == "chat").all()
        assert len(chat_logs) == 1
    
    def test_query_by_status_code(self, test_db):
        """Test filtering logs by status code."""
        # Add test data
        for status in [200, 200, 404, 500]:
            log = RequestLog(
                request_id=f"123e4567-e89b-12d3-a456-4266141740{status}",
                method="GET",
                path="/api/test",
                service="test",
                status_code=status,
                response_time_ms=50.0,
                client_ip="192.168.1.1",
                retry_count=0,
                circuit_breaker_state="CLOSED"
            )
            test_db.add(log)
        
        test_db.commit()
        
        # Query by status code
        success_logs = test_db.query(RequestLog).filter(RequestLog.status_code == 200).all()
        assert len(success_logs) == 2
        
        error_logs = test_db.query(RequestLog).filter(RequestLog.status_code >= 400).all()
        assert len(error_logs) == 2
    
    def test_query_by_time_range(self, test_db):
        """Test filtering logs by timestamp."""
        now = datetime.utcnow()
        
        # Add old log
        old_log = RequestLog(
            request_id="123e4567-e89b-12d3-a456-426614174000",
            method="GET",
            path="/api/test",
            service="test",
            status_code=200,
            response_time_ms=50.0,
            client_ip="192.168.1.1",
            timestamp=now - timedelta(hours=2),
            retry_count=0,
            circuit_breaker_state="CLOSED"
        )
        test_db.add(old_log)
        
        # Add recent log
        recent_log = RequestLog(
            request_id="223e4567-e89b-12d3-a456-426614174000",
            method="GET",
            path="/api/test",
            service="test",
            status_code=200,
            response_time_ms=50.0,
            client_ip="192.168.1.1",
            timestamp=now - timedelta(minutes=5),
            retry_count=0,
            circuit_breaker_state="CLOSED"
        )
        test_db.add(recent_log)
        
        test_db.commit()
        
        # Query last hour
        one_hour_ago = now - timedelta(hours=1)
        recent_logs = test_db.query(RequestLog).filter(
            RequestLog.timestamp >= one_hour_ago
        ).all()
        assert len(recent_logs) == 1
    
    def test_query_statistics(self, test_db):
        """Test calculating statistics from logs."""
        # Add test data
        logs_data = [
            ("GET", 200, 50.0),
            ("GET", 200, 60.0),
            ("POST", 201, 120.0),
            ("GET", 500, 30.0),
        ]
        
        for i, (method, status, time_ms) in enumerate(logs_data):
            log = RequestLog(
                request_id=f"123e4567-e89b-12d3-a456-42661417400{i}",
                method=method,
                path=f"/api/test/{i}",
                service="test",
                status_code=status,
                response_time_ms=time_ms,
                client_ip="192.168.1.1",
                retry_count=0,
                circuit_breaker_state="CLOSED"
            )
            test_db.add(log)
        
        test_db.commit()
        
        # Calculate stats
        logs = test_db.query(RequestLog).all()
        
        assert len(logs) == 4
        avg_response_time = sum(l.response_time_ms for l in logs) / len(logs)
        assert avg_response_time == 65.0
        
        error_count = len([l for l in logs if l.status_code >= 400])
        assert error_count == 1
    
    def test_query_by_client_ip(self, test_db):
        """Test filtering logs by client IP."""
        # Add test data
        for ip in ["192.168.1.1", "192.168.1.1", "192.168.1.2"]:
            log = RequestLog(
                request_id=f"123e4567-e89b-12d3-a456-4266141740{ip.split('.')[-1]}",
                method="GET",
                path="/api/test",
                service="test",
                status_code=200,
                response_time_ms=50.0,
                client_ip=ip,
                retry_count=0,
                circuit_breaker_state="CLOSED"
            )
            test_db.add(log)
        
        test_db.commit()
        
        # Query by IP
        ip_logs = test_db.query(RequestLog).filter(
            RequestLog.client_ip == "192.168.1.1"
        ).all()
        assert len(ip_logs) == 2


class TestCircuitBreakerState:
    """Test circuit breaker state tracking in logs."""
    
    def test_log_circuit_breaker_states(self, test_db):
        """Test logging different circuit breaker states."""
        states = ["CLOSED", "HALF_OPEN", "OPEN"]
        
        for i, state in enumerate(states):
            log = RequestLog(
                request_id=f"123e4567-e89b-12d3-a456-42661417400{i}",
                method="GET",
                path="/api/test",
                service="test",
                status_code=200,
                response_time_ms=50.0,
                client_ip="192.168.1.1",
                retry_count=i,
                circuit_breaker_state=state
            )
            test_db.add(log)
        
        test_db.commit()
        
        # Verify states logged
        for i, state in enumerate(states):
            log = test_db.query(RequestLog).filter(
                RequestLog.circuit_breaker_state == state
            ).first()
            assert log is not None
            assert log.circuit_breaker_state == state


class TestRetryTracking:
    """Test retry count tracking in logs."""
    
    def test_log_retry_counts(self, test_db):
        """Test logging retry attempts."""
        # Log with different retry counts
        for retry_count in [0, 1, 2, 3]:
            log = RequestLog(
                request_id=f"123e4567-e89b-12d3-a456-42661417400{retry_count}",
                method="GET",
                path="/api/test",
                service="test",
                status_code=200,
                response_time_ms=50.0 + (retry_count * 10),  # More time with more retries
                client_ip="192.168.1.1",
                retry_count=retry_count,
                circuit_breaker_state="CLOSED"
            )
            test_db.add(log)
        
        test_db.commit()
        
        # Query logs with retries
        with_retries = test_db.query(RequestLog).filter(
            RequestLog.retry_count > 0
        ).all()
        assert len(with_retries) == 3
        
        no_retries = test_db.query(RequestLog).filter(
            RequestLog.retry_count == 0
        ).all()
        assert len(no_retries) == 1
