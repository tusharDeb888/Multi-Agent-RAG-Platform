# IOC Secure Knowledge AI (ISK-AI)

## Prerequisites
- Python 3.10+
- Oracle Instant Client (if using Oracle DB)
- Tesseract OCR (for document ingestion)

## Setup

1.  **Create Virtual Environment**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Configure Environment**:
    Copy `.env.example` to `.env`:
    ```bash
    cp .env.example .env
    ```
    
    By default, the app is configured to use **SQLite** (`dev.db`) for easy local development.
    To use **Oracle**, uncomment the Oracle configuration lines in `.env` and comment out `CUSTOM_DATABASE_URL`.

4.  **Initialize Database**:
    The application automatically creates tables on startup in development mode.

## Running the Application

Start the server using Uvicorn:

```bash
uvicorn app.main:app --reload
```

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Root**: [http://localhost:8000/api/v1](http://localhost:8000/api/v1)

## Running Tests

To run tests, use `python -m pytest` from the project root:

```bash
python -m pytest tests/
```

**Note**: Do not run `pytest` directly or `python tests/test_api.py` as it may cause module import errors.

## Features

- **Document Ingestion**: Upload PDFs via `/api/v1/documents/upload`.
- **RAG Chat**: Query documents via `/api/v1/chat/query`.
- **Authentication**: Login via `/api/v1/auth/login`.
# IOCL-RAG-System
