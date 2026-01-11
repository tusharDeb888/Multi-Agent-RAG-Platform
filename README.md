# ISK-AI (IOC Secure Knowledge AI)

**Enterprise-Grade Zero-Trust RAG System**  
*Securely chat with your internal documents using local AI.*

---

## 🚀 Quick Start (Production)

The easiest way to run the full system (Backend, Frontend, Database, AI) is via Docker.

```bash
# 1. Clone the repository
git clone https://github.com/your-org/IOCL-RAG.git
cd IOCL-RAG

# 2. Configure Environment
cp .env.example .env
# (Edit .env with your secrets if needed)

# 3. Start the Application
docker-compose up -d --build
```

*   **Frontend**: [http://localhost:3000](http://localhost:3000)
*   **Backend API**: [http://localhost:8000/docs](http://localhost:8000/docs)
*   **Milvus Console**: [http://localhost:9091](http://localhost:9091)

---

## 📚 Documentation

We have detailed documentation available for every aspect of the project:

| Document | Description | Target Audience |
| :--- | :--- | :--- |
| **[Documentation.md](./Documentation.md)** | **User Manual & Overview**. Features, How to Chat, How to Upload. | Users & Admins |
| **[INSTRUCTION.md](./INSTRUCTION.md)** | **Deployment Guide**. Production setup, CORS, SSL, Local LLMs (Ollama). | DevOps & Leads |
| **[SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md)** | **Technical Deep Dive**. Diagrams, component breakdown, and data flow. | Developers |

---

## 💡 Key Features

*   **Zero-Trust Security**: No data leaves the server. RBAC ensures authorized access only.
*   **Accurate RAG**: Hybrid retrieval (Vector + Keyword) with Cross-Encoder reranking.
*   **Multi-Format**: Supports PDF, Excel, Word, and PowerPoint.
*   **Local Inference**: Powered by **Llama 3** and **Ollama** for total data sovereignty.
*   **Smart Ingestion**: Automatic OCR and Vision AI fallback for scanned documents and charts.

---

## 🛠️ Development Setup (Local)

If you want to contribute code without Docker:

1.  **Backend**:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements-dev.txt
    uvicorn app.main:app --reload
    ```

2.  **Frontend**:
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

For troubleshooting and logic details, refer to [SYSTEM_ARCHITECTURE.md](./SYSTEM_ARCHITECTURE.md).
