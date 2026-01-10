# Production Deployment & Power-User Guide

This guide outlines the critical steps to deploy the ISK-AI RAG system in a production environment and how to configure it to use powerful local LLMs (like Llama 3 70B).

---

## 1. Environment Setup

For production, you must create a dedicated `.env` file (e.g., `.env.prod`) or set these variables in your deployment environment (Docker, Kubernetes, etc.).

### Critical Configuration Changes

| Variable | Development Value | **Production Value** | Description |
| :--- | :--- | :--- | :--- |
| `ENVIRONMENT` | `development` | `production` | Disables debug mode and enables optimizations. |
| `LOG_LEVEL` | `INFO` | `WARNING` or `INFO` | Reduces log verbosity for performance. |
| `BACKEND_CORS_ORIGINS` | `["http://localhost:5173"]` | `["https://your-domain.com"]` | **CRITICAL**: Whitelist ONLY your frontend domain. |
| `SECRET_KEY` | *(Random)* | **(Long Random String)** | Use `openssl rand -hex 32` to generate. |
| `ENCRYPTION_KEY` | *(Random)* | **(32-byte Base64 Key)** | Required for at-rest encryption. |

---

## 2. Using Powerful Local LLMs (Ollama)

To replace the default small model with a powerful local model (e.g., Llama 3 70B, Mixtral 8x7B) for production-grade reasoning:

### A. Prerequisites
1.  **Hardware**: Ensure your server has sufficient VRAM.
    *   Llama 3 8B: ~16GB RAM + GPU (optional but recommended)
    *   Llama 3 70B: ~48GB+ GPU VRAM (e.g., A6000, A100) or high-RAM Mac Studio (M2/M3 Ultra).
2.  **Ollama**: Install [Ollama](https://ollama.com/) on the server.

### B. Pull the Model
Run this command on your server to download the model weights:
```bash
ollama pull llama3:70b
# OR for a smaller but powerful option:
ollama pull llama3:8b-instruct-q8_0
```

### C. Configure `.env`
Update your environment variables to point to this new model:

```ini
# 1. Set Provider to Ollama
LLM_PROVIDER=ollama

# 2. Set the Model Tag (MUST match the tag used in 'ollama pull')
# Example: 'llama3:70b' or 'mixtral'
LLM_MODEL_PATH=llama3:70b

# 3. Increase Context Window (If hardware permits)
# Llama 3 supports up to 8192 by default context
LLM_CONTEXT_LENGTH=8192

# 4. Point to Ollama Instance
OLLAMA_BASE_URL=http://localhost:11434
```

---

## 3. CORS Configuration (Cross-Origin Resource Sharing)

Strict CORS is mandatory for production security.

In your `.env` file, set `BACKEND_CORS_ORIGINS` to a JSON-formatted list of allowed frontend domains.

**Example:**
```ini
BACKEND_CORS_ORIGINS=["https://rag.indian-oil.com", "https://admin.indian-oil.com"]
```

**Notes:**
*   Do NOT use `*` or `["*"]` in production.
*   Ensure protocol (`https://`) matches exactly.
*   Remove trailing slashes (e.g., use `https://site.com`, not `https://site.com/`).

---

## 4. Performance & Security Best Practices

### Vector Database (Milvus)
Ensure Milvus is running in production mode via Docker.
*   **Persistence**: Ensure `./volumes/milvus` is mapped to a persistent high-speed disk (SSD/NVMe).
*   **Token**: If you enable Milvus authentication, set `MILVUS_TOKEN` in `.env`.

### Database (Oracle)
*   **Connection Pooling**: logic is handled by `oracledb`. Adjust `ORACLE_POOL_SIZE` in `.env` based on expected concurrency (Default: 10, Prod: 20-50).

### API Security
*   **Rate Limiting**: Configured via Redis. Ensure Redis is persistent.
    *   Env: `RATE_LIMIT_DEFAULT="100/minute"` (Adjust as needed).

## 5. Production Infrastructure (Critical)

### A. Filesystem Persistence
If you are using Docker or Cloud storage, you **MUST** persist the data directory.
*   **Path**: `./data` (or wherever your `index_storage_path` points).
*   **Reason**: This folder contains uploaded documents, vector indices, and SQLite databases (if used). If you restart the container without a volume mount, **ALL DATA WILL BE LOST**.
*   **Docker Example**:
    ```yaml
    volumes:
      - ./volumes/data:/app/data
    ```

### B. SSL/HTTPS
Do not run Uvicorn directly on port 80/443 exposed to the web.
*   **Action**: Use Nginx or a Load Balancer (AWS ALB, Cloudflare) in front of the application to handle SSL termination.
*   **Config**: Forward headers `X-Forwarded-For` and `X-Forwarded-Proto` so the rate limiter works correctly.

## 6. Deployment Commands

**1. Database Migration (If applicable)**
```bash
# Production typically relies on DBA-managed schemas, but if using Alembic:
alembic upgrade head
```

**2. Start Backend (Production Workers)**
```bash
# Run with Gunicorn/Uvicorn for concurrency
# Example: 4 Workers
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:8000
```
*Note: Make sure to activate your python environment (`venv`) first.*

**3. Build Frontend**
```bash
cd frontend
npm install
npm run build
# Serve the 'dist' folder via Nginx or the Backend's static file handler
```

---

## 6. Code & Configuration Verification

While most settings are handled via `.env`, you should verify these specific files to ensure they align with your production infrastructure.

### A. Frontend API Connection
**File**: `frontend/src/services/api.js`

*   **Current Logic**:
    ```javascript
    const API_URL = import.meta.env.VITE_API_URL || '/api/v1';
    ```
*   **Production Action**:
    *   If your Backend and Frontend are on the **SAME** domain (e.g., `app.com`), no change is needed. It will use the relative path `/api/v1`.
    *   If they are on **DIFFERENT** domains (e.g., `front.com` and `api.back.com`), you must create a file named `frontend/.env.production` and add:
        ```ini
        VITE_API_URL=https://api.back.com/api/v1
        ```

### B. Backend Default Settings
**File**: `app/core/config.py`

*   **Check**: Verify the `Settings` class defaults.
*   **Action**: If you cannot use environment variables for some reason, hardcode your production defaults here (Not recommended, but possible).
    *   Confirm `backend_cors_origins` parsing logic supports your domain structure.

### C. Authentication (Optional)
**File**: `app/core/security.py` / `app/application/services/auth_service.py`

*   **Action**: The current system uses a self-contained JWT implementation.
    *   If integrating with **LDAP/Active Directory** or **OAuth2** (Google/Microsoft), you will need to modify `auth_service.py` to validate credentials against the external provider instead of the local database.

### D. Critical: Database Tables
**File**: `app/main.py`

*   **Current Logic**:
    ```python
    if settings.is_development:
        Base.metadata.create_all(bind=engine)
    ```
*   **Production Action**:
    *   **Option 1 (Recommended)**: Set up Alembic migrations (`alembic init alembic`, `alembic revision --autogenerate`, `alembic upgrade head`).
    *   **Option 2 (Quick Start)**: If this is the **first** production run and you have no data, you can temporarily comment out the `if settings.is_development:` check to let the app create tables, then uncomment it.
    *   **Warning**: If you do not do this, the application will start but fail when trying to read/write to the database.
