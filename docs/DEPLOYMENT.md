# Deployment Guide

Complete guide for deploying the Complaint Generator system to production environments.

## Overview

This guide covers deployment strategies for:
- **Local Development** - Running on your workstation
- **Single Server** - Simple production deployment
- **Container Deployment** - Docker/Kubernetes
- **Cloud Platforms** - AWS, GCP, Azure

## Prerequisites

### System Requirements

**Minimum:**
- CPU: 2 cores
- RAM: 4 GB
- Storage: 10 GB
- OS: Linux (Ubuntu 20.04+), macOS, Windows with WSL2

**Recommended for Production:**
- CPU: 4+ cores
- RAM: 8+ GB
- Storage: 50+ GB SSD
- OS: Linux (Ubuntu 22.04 LTS)

### Software Dependencies

- Python 3.8+
- Git
- (Optional) Docker 20.10+
- (Optional) IPFS daemon for distributed storage

## Local Development

### 1. Clone Repository

```bash
git clone https://github.com/endomorphosis/complaint-generator.git
cd complaint-generator
```

### 2. Initialize Submodules

```bash
git submodule update --init --recursive
```

### 3. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Environment

Create `.env` file:
```bash
# Development .env
OPENAI_API_KEY=sk-...
BRAVE_SEARCH_API_KEY=...
JWT_SECRET_KEY=dev-secret-change-in-production
SERVER_HOSTNAME=http://localhost:8000
LOG_LEVEL=DEBUG
```

### 6. Run Application

```bash
# CLI mode
python run.py --config config.llm_router.json

# Server mode (edit config to enable server)
python run.py --config config.llm_router.json

# Dedicated review surface mode
python run.py --config config.review_surface.json
```

Access at: http://localhost:8000

For the focused operator workflow, `config.review_surface.json` starts only the claim-support dashboard and its review/follow-up API routes. The dashboard is available at `http://localhost:8000/claim-support-review`, and the dedicated review app exposes `http://localhost:8000/health` for lightweight health checks. The dashboard surfaces current coverage, follow-up signals, recent follow-up history, and manual-review resolution controls from the same review payloads used by the API.

## Single Server Deployment

### Production Server Setup

#### 1. Provision Server

Use a cloud provider or dedicated server:
- Ubuntu 22.04 LTS
- 4 CPU cores, 8 GB RAM
- 50 GB SSD storage
- Static IP address

#### 2. Initial Server Configuration

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3.10 python3.10-venv python3-pip git nginx

# Create application user
sudo useradd -m -s /bin/bash complaint-app
sudo su - complaint-app
```

#### 3. Deploy Application

```bash
# Clone repository
git clone https://github.com/endomorphosis/complaint-generator.git
cd complaint-generator
git submodule update --init --recursive

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create production directories
mkdir -p logs statefiles
chmod 700 statefiles
```

#### 4. Configure Environment

Create `/home/complaint-app/.env`:
```bash
OPENAI_API_KEY=sk-prod-...
BRAVE_SEARCH_API_KEY=...
JWT_SECRET_KEY=<generate-securely>
SERVER_HOSTNAME=https://yourdomain.com
LOG_LEVEL=INFO
DATABASE_PATH=/home/complaint-app/complaint-generator/statefiles
```

**Generate secure JWT key:**
```bash
# Python 3.6+ (recommended)
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Python 2.7 or 3.5 and earlier
python -c "import os; import base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

#### 5. Create systemd Service

Create `/etc/systemd/system/complaint-generator.service`:

```ini
[Unit]
Description=Complaint Generator API Server
After=network.target

[Service]
Type=simple
User=complaint-app
Group=complaint-app
WorkingDirectory=/home/complaint-app/complaint-generator
Environment="PATH=/home/complaint-app/complaint-generator/venv/bin"
EnvironmentFile=/home/complaint-app/.env
ExecStart=/home/complaint-app/complaint-generator/venv/bin/python run.py --config config.llm_router.json
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/complaint-app/complaint-generator/statefiles /home/complaint-app/complaint-generator/logs

[Install]
WantedBy=multi-user.target
```

Enable and start service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable complaint-generator
sudo systemctl start complaint-generator
sudo systemctl status complaint-generator
```

#### 5a. Review Surface Service

If you only want the claim-support operator surface, create a dedicated service that uses `config.review_surface.json`:

Create `/etc/systemd/system/complaint-generator-review.service`:

```ini
[Unit]
Description=Complaint Generator Review Surface
After=network.target

[Service]
Type=simple
User=complaint-app
Group=complaint-app
WorkingDirectory=/home/complaint-app/complaint-generator
Environment="PATH=/home/complaint-app/complaint-generator/venv/bin"
EnvironmentFile=/home/complaint-app/.env
ExecStart=/home/complaint-app/complaint-generator/venv/bin/python run.py --config config.review_surface.json
Restart=always
RestartSec=10

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/complaint-app/complaint-generator/statefiles /home/complaint-app/complaint-generator/logs

[Install]
WantedBy=multi-user.target
```

Enable and start the review surface:

```bash
sudo systemctl daemon-reload
sudo systemctl enable complaint-generator-review
sudo systemctl start complaint-generator-review
sudo systemctl status complaint-generator-review
```

#### 6. Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/complaint-generator`:

```nginx
upstream complaint_backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;
    
    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Logging
    access_log /var/log/nginx/complaint-generator-access.log;
    error_log /var/log/nginx/complaint-generator-error.log;
    
    # Max upload size
    client_max_body_size 10M;
    
    # Proxy settings
    location / {
        proxy_pass http://complaint_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # WebSocket support
    location /api/chat {
        proxy_pass http://complaint_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # Static files (if serving directly)
    location /static/ {
        alias /home/complaint-app/complaint-generator/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

For the review surface, the same reverse proxy pattern applies. The key operator routes are:

- `/claim-support-review`
- `/api/claim-support/review`
- `/api/claim-support/execute-follow-up`

You can verify the service behind Nginx with a simple smoke check:

```bash
curl -I http://127.0.0.1:8000/claim-support-review
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/complaint-generator /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 7. Configure SSL with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Auto-renewal
sudo systemctl enable certbot.timer
```

#### 8. Configure Firewall

```bash
# UFW firewall
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### Monitoring & Maintenance

#### Log Monitoring

```bash
# Application logs
sudo journalctl -u complaint-generator -f

# Nginx logs
sudo tail -f /var/log/nginx/complaint-generator-access.log
sudo tail -f /var/log/nginx/complaint-generator-error.log
```

#### Health Checks

The legacy full web server still does not expose a dedicated `/health` endpoint. For basic availability checks use:

- Full web server: `/`
- Dedicated review surface: `/health`

Setup monitoring with cron:
```bash
# /etc/cron.d/complaint-generator-health
*/5 * * * * root curl -f http://localhost:8000/ || systemctl restart complaint-generator
```

For the dedicated review surface service, probe `/health` instead:

```bash
*/5 * * * * root curl -f http://localhost:8000/health || systemctl restart complaint-generator-review
```

#### Backups

```bash
#!/bin/bash
# /home/complaint-app/backup.sh

BACKUP_DIR="/var/backups/complaint-generator"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
cp -r /home/complaint-app/complaint-generator/statefiles $BACKUP_DIR/statefiles_$DATE

# Backup logs
tar czf $BACKUP_DIR/logs_$DATE.tar.gz /home/complaint-app/complaint-generator/logs

# Keep only last 7 days
find $BACKUP_DIR -mtime +7 -delete

# Upload to S3 (optional)
# aws s3 sync $BACKUP_DIR s3://your-bucket/backups/
```

Add to crontab:
```bash
0 2 * * * /home/complaint-app/backup.sh
```

## Docker Deployment

### Dockerfile

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Initialize submodules
RUN git submodule update --init --recursive || true

# Create directories
RUN mkdir -p statefiles logs && \
    chmod 700 statefiles

# Non-root user
RUN useradd -m -u 1000 complaint-app && \
    chown -R complaint-app:complaint-app /app
USER complaint-app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/', timeout=5).raise_for_status()"

# Run application
CMD ["python", "run.py", "--config", "config.llm_router.json"]
```

To build a review-surface-only image, swap the startup command:

```dockerfile
CMD ["python", "run.py", "--config", "config.review_surface.json"]
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  app:
    build: .
    image: complaint-generator:latest
    container_name: complaint-generator
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - BRAVE_SEARCH_API_KEY=${BRAVE_SEARCH_API_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - SERVER_HOSTNAME=${SERVER_HOSTNAME}
      - LOG_LEVEL=INFO
    volumes:
      - ./statefiles:/app/statefiles
      - ./logs:/app/logs
      - ./config.llm_router.json:/app/config.llm_router.json:ro
    networks:
      - complaint-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  complaint-network:
    driver: bridge

volumes:
  statefiles:
  logs:
```

For the dedicated review surface, mount `config.review_surface.json` instead and start with that config:

```yaml
    volumes:
      - ./config.review_surface.json:/app/config.review_surface.json:ro
```

For a review-surface-only container healthcheck, target the dedicated health route:

```yaml
    healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
```

```bash
docker run --rm -p 8000:8000 \
  -v "$PWD/config.review_surface.json:/app/config.review_surface.json:ro" \
  complaint-generator:latest \
  python run.py --config config.review_surface.json
```

### Build and Run

```bash
# Build image
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Kubernetes Deployment

### Deployment Manifest

Create `k8s/deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: complaint-generator
  labels:
    app: complaint-generator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: complaint-generator
  template:
    metadata:
      labels:
        app: complaint-generator
    spec:
      containers:
      - name: complaint-generator
        image: your-registry/complaint-generator:latest
        ports:
        - containerPort: 8000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: complaint-secrets
              key: openai-api-key
        - name: JWT_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: complaint-secrets
              key: jwt-secret-key
        - name: LOG_LEVEL
          value: "INFO"
        resources:
          requests:
            memory: "1Gi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 8000
          initialDelaySeconds: 20
          periodSeconds: 5
        volumeMounts:
        - name: statefiles
          mountPath: /app/statefiles
      volumes:
      - name: statefiles
        persistentVolumeClaim:
          claimName: complaint-generator-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: complaint-generator-service
spec:
  selector:
    app: complaint-generator
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8000
  type: LoadBalancer
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: complaint-generator-pvc
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
```

### Secrets

Create secrets:
```bash
kubectl create secret generic complaint-secrets \
  --from-literal=openai-api-key='sk-...' \
  --from-literal=jwt-secret-key='...' \
  --from-literal=brave-search-key='...'
```

### Deploy

```bash
kubectl apply -f k8s/deployment.yaml
kubectl get pods
kubectl logs -f deployment/complaint-generator
```

## Cloud Platform Deployment

### AWS (Elastic Beanstalk)

1. Install EB CLI: `pip install awsebcli`
2. Initialize: `eb init`
3. Create environment: `eb create production`
4. Deploy: `eb deploy`

### Google Cloud (Cloud Run)

```bash
# Build and push image
gcloud builds submit --tag gcr.io/your-project/complaint-generator

# Deploy
gcloud run deploy complaint-generator \
  --image gcr.io/your-project/complaint-generator \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars OPENAI_API_KEY=$OPENAI_API_KEY
```

### Azure (Container Instances)

```bash
az container create \
  --resource-group complaint-generator-rg \
  --name complaint-generator \
  --image your-registry/complaint-generator:latest \
  --dns-name-label complaint-generator \
  --ports 8000 \
  --environment-variables \
    OPENAI_API_KEY=$OPENAI_API_KEY \
    JWT_SECRET_KEY=$JWT_SECRET_KEY
```

## Performance Tuning

### Application Configuration

```json
{
  "APPLICATION": {
    "workers": 4,
    "timeout": 60,
    "keepalive": 5
  }
}
```

### Nginx Tuning

```nginx
worker_processes auto;
worker_rlimit_nofile 65535;

events {
    worker_connections 4096;
    use epoll;
}

http {
    # Connection pooling
    keepalive_timeout 65;
    keepalive_requests 100;
    
    # Compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_types text/plain text/css text/json application/json;
}
```

### Database Optimization

```python
# Connection pooling
import duckdb

conn = duckdb.connect('statefiles/data.duckdb', config={
    'max_memory': '2GB',
    'threads': 4,
    'enable_object_cache': True
})
```

## Troubleshooting

### Common Issues

**Service won't start:**
```bash
sudo journalctl -u complaint-generator -n 100 --no-pager
```

**High memory usage:**
```bash
# Restart service
sudo systemctl restart complaint-generator

# Check for memory leaks
ps aux | grep python
```

**Database locked:**
```bash
# Close all connections
sudo systemctl stop complaint-generator
rm statefiles/*.duckdb-wal
sudo systemctl start complaint-generator
```

## Related Documentation

- [Configuration Guide](CONFIGURATION.md)
- [Security Guide](SECURITY.md)
- [Applications Guide](APPLICATIONS.md)
- [Architecture](ARCHITECTURE.md)

## Support

For deployment assistance:
- GitHub Issues: https://github.com/endomorphosis/complaint-generator/issues
- GitHub Discussions: https://github.com/endomorphosis/complaint-generator/discussions
