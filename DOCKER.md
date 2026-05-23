# Docker Deployment Guide — Smart API Gateway

## Overview

This guide explains how to run the entire Smart API Gateway stack using Docker. The setup includes:
- **Gateway** (Port 8000) — Main API Gateway
- **Auth Service** (Port 9001) — Mock Authentication
- **Chat Service** (Port 9002) — Mock Chat
- **AI Service** (Port 9003) — Mock AI
- **Redis** (Port 6379) — Caching & Rate Limiting
- **PostgreSQL** (Port 5432) — Database & Logging

---

## Port Mapping (NO COLLISIONS)

| Service | Internal Port | External Port | Purpose |
|---------|---------------|---------------|---------|
| **Gateway** | 8000 | 8000 | Main entry point |
| **Auth Service** | 9001 | 9001 | Authentication |
| **Chat Service** | 9002 | 9002 | Chat operations |
| **AI Service** | 9003 | 9003 | AI operations |
| **Redis** | 6379 | 6379 | Cache & rate limit state |
| **PostgreSQL** | 5432 | 5432 | Database |

**Network**: All services communicate internally via `gateway-network` bridge network, allowing:
- Gateway → Auth/Chat/AI using container names (e.g., `http://auth:9001`)
- No external network overhead for internal communication
- Services are isolated from each other except via gateway

---

## Quick Start

### 1. Build All Images
```bash
cd docker
docker-compose build
```

### 2. Start the Stack
```bash
# Start all services in background
docker-compose up -d

# Follow logs in real-time
docker-compose logs -f gateway
```

### 3. Verify Services Are Running
```bash
# Check all containers
docker-compose ps

# Test gateway health
curl http://localhost:8000/health

# Test auth service
curl http://localhost:8000/auth/health

# Check rate limit status
curl http://localhost:8000/gateway/ratelimit
```

### 4. Stop the Stack
```bash
# Stop all services (keep data)
docker-compose stop

# Remove all containers (keep volumes)
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

---

## API Endpoints (via Gateway)

### Gateway Health
```bash
curl http://localhost:8000/health
```

### Routing Table
```bash
curl http://localhost:8000/gateway/routes
```

### Rate Limit Status
```bash
curl http://localhost:8000/gateway/ratelimit
```

### Auth Service
```bash
# Get health
curl http://localhost:8000/auth/health

# Login
curl -X POST http://localhost:8000/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"secret"}'

# Get current user
curl http://localhost:8000/auth/me \
  -H 'Authorization: Bearer mock-jwt-token-abc123'
```

### Chat Service
```bash
# List rooms
curl http://localhost:8000/chat/rooms

# Get room messages
curl http://localhost:8000/chat/rooms/general/messages

# Send message
curl -X POST http://localhost:8000/chat/rooms/general/messages \
  -H 'Content-Type: application/json' \
  -d '{"sender":"user1","text":"Hello"}'
```

### AI Service
```bash
# List models
curl http://localhost:8000/ai/models

# Complete prompt
curl -X POST http://localhost:8000/ai/complete \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What is a reverse proxy?"}'

# Summarize text
curl -X POST http://localhost:8000/ai/summarize \
  -H 'Content-Type: application/json' \
  -d '{"text":"Long text here..."}'
```

---

## Environment Variables

### For Development
```bash
# docker-compose.yml already sets these:
AUTH_SERVICE_URL=http://auth:9001
CHAT_SERVICE_URL=http://chat:9002
AI_SERVICE_URL=http://ai:9003
REDIS_URL=redis://redis:6379
DATABASE_URL=postgresql://gateway:gateway_password@postgres:5432/gateway_logs
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### To Override
```bash
# Create docker-compose.override.yml (not tracked by git)
version: "3.9"
services:
  gateway:
    environment:
      - LOG_LEVEL=DEBUG
      - ENVIRONMENT=production
```

---

## Database Access

### Connect to PostgreSQL
```bash
# From host machine
psql postgresql://gateway:gateway_password@localhost:5432/gateway_logs

# Or from inside container
docker-compose exec postgres psql -U gateway -d gateway_logs

# List tables
\dt

# View request logs
SELECT id, request_id, service, status_code, created_at FROM request_logs LIMIT 10;
```

---

## Redis Access

### Connect to Redis
```bash
# Using redis-cli from host
redis-cli -p 6379

# Or from inside container
docker-compose exec redis redis-cli

# Common commands
PING                      # Test connection
KEYS *                    # List all keys
GET <key>                 # Get value
FLUSHALL                  # Clear all data
```

---

## Logs

### View Service Logs
```bash
# Gateway logs
docker-compose logs -f gateway

# All logs
docker-compose logs -f

# Specific service
docker-compose logs -f auth

# Last 100 lines
docker-compose logs --tail=100 gateway

# Timestamps
docker-compose logs -f --timestamps gateway
```

---

## Testing Inside Docker

### Run Tests
```bash
# Run all tests
docker-compose exec gateway pytest tests/ -v

# Run specific test file
docker-compose exec gateway pytest tests/test_gateway.py -v

# Run with coverage
docker-compose exec gateway pytest tests/ --cov=gateway

# Run demo tests
docker-compose exec gateway pytest tests/test_demo_retry_circuit_breaker.py -v -s
```

---

## Troubleshooting

### Port Already in Use
```bash
# Find what's using the port
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or change the port in docker-compose.yml:
# ports:
#   - "8001:8000"  # Use 8001 instead
```

### Database Connection Failed
```bash
# Check if postgres is healthy
docker-compose ps postgres

# Check postgres logs
docker-compose logs postgres

# Wait longer for startup
docker-compose up -d postgres
sleep 10
docker-compose up -d gateway
```

### Redis Connection Failed
```bash
# Check redis
docker-compose ps redis

# Restart redis
docker-compose restart redis
```

### Services Not Found
```bash
# Rebuild images
docker-compose build --no-cache

# Check network
docker network ls
docker network inspect gateway_network

# Restart everything
docker-compose down
docker-compose up -d
```

### Performance Issues
```bash
# Check resource usage
docker stats

# Increase limits in docker-compose.yml:
# deploy:
#   resources:
#     limits:
#       cpus: '1'
#       memory: 512M
```

---

## Production Deployment

### Security Considerations
1. **Change database password** in docker-compose.yml
2. **Use environment variables** for secrets (.env file)
3. **Enable HTTPS** (add reverse proxy like Nginx)
4. **Restrict Redis** access (password, firewall)
5. **Set `ENVIRONMENT=production`** in gateway

### Performance Tuning
```yaml
# docker-compose.yml adjustments:
redis:
  command: redis-server --maxmemory 2gb --maxmemory-policy allkeys-lru

postgres:
  environment:
    POSTGRES_INITDB_ARGS: "-c shared_buffers=256MB -c max_connections=200"

gateway:
  command: uvicorn gateway.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Monitoring
```bash
# Use Portainer for UI management
docker run -d -p 9000:9000 portainer/portainer-ce

# Use prometheus + grafana for metrics
# See docker-compose.override.yml for example
```

---

## File Structure

```
docker/
├── Dockerfile              # Multi-stage build for all services
├── docker-compose.yml      # Complete stack definition
├── DOCKER.md              # This file
├── .dockerignore           # Files excluded from build context
└── docker-compose.prod.yml # Production overrides (optional)

Root:
├── requirements.txt        # Python dependencies
├── gateway/                # Gateway application
├── services/               # Auth, Chat, AI services
├── tests/                  # Test suite (runs in container)
└── init-db.sql            # Database initialization script
```

---

## Common Tasks

### Access Container Shell
```bash
# Gateway shell
docker-compose exec gateway bash

# PostgreSQL shell
docker-compose exec postgres bash

# Run Python commands
docker-compose exec gateway python -c "import gateway; print(gateway.__file__)"
```

### Rebuild After Code Changes
```bash
# Rebuild and restart
docker-compose up -d --build gateway

# Or rebuild specific service
docker-compose up -d --build auth
```

### View Real-Time Metrics
```bash
# CPU, Memory, Network usage
docker stats

# Specific container
docker stats gateway_main
```

### Backup Database
```bash
# Dump database
docker-compose exec postgres pg_dump -U gateway gateway_logs > backup.sql

# Restore from backup
docker-compose exec -T postgres psql -U gateway gateway_logs < backup.sql
```

---

## Next Steps

1. **Run tests**: `docker-compose exec gateway pytest tests/ -v`
2. **Check logs**: `docker-compose logs -f gateway`
3. **Load test**: Use `curl` or `ab` to stress test
4. **Monitor**: Watch `docker stats` for resource usage

---

## Support

- Check logs: `docker-compose logs <service>`
- Inspect container: `docker-compose exec <service> bash`
- Rebuild: `docker-compose build --no-cache`
- Reset: `docker-compose down -v && docker-compose up -d`
