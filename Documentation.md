# Project Documentation: ISK-AI (Internal Search & Knowledge AI)

**Version:** 1.0.0  
**Last Updated:** January 2026

---

## 1. Introduction

**ISK-AI** is an advanced Retrieval-Augmented Generation (RAG) system built for secure, internal enterprise knowledge management. It allows authorized users to upload documents (PDF, Excel, Word), index them using vector search technology, and query information using natural language.

Unlike standard chatbots, ISK-AI adheres to a **Zero-Trust** philosophy:
*   **No Hallucinations:** It answers *only* from the uploaded documents.
*   **Strict Access Control:** Users can only search documents they have permission to view.
*   **Total Privacy:** All AI processing is local; no data leaves the secure infrastructure.

---

## 2. Key Features

### 🔍 **Intelligent Search (RAG)**
*   **Context-Aware**: Understands the meaning of your query, not just keywords (e.g., "revenue growth" matches "increase in sales").
*   **Citations**: Every answer includes footnote citations linking back to the exact source document and page number.
*   **Hybrid Retrieval**: Combines semantic vector search with precise keyword matching for optimal accuracy.

### 📂 **Document Management**
*   **Multi-Format Support**: Upload PDF, DOCX, XLSX, PPTX, and CSV files.
*   **Smart Ingestion**:
    *   **OCR**: Automatically extracts text from scanned images/PDFs.
    *   **Vision AI**: Analyzes charts and handwriting in documents.
*   **Department Isolation**: Documents are tagged by department (e.g., HR, Finance) for access control.

### 💬 **Interactive Chat Interface**
*   **History**: Save and resume past conversation threads.
*   **Streaming**: Answers appear token-by-token for a responsive experience.
*   **Feedback**: Regenerate answers or copy them with a single click.

### 🛡️ **Enterprise Security**
*   **Role-Based Access Control (RBAC)**: Admins, Managers, and Users have distinct permissions.
*   **Audit Logging**: Every search query and document access is logged for compliance.
*   **Local Inference**: Uses local LLMs (Llama 3, Ollama) ensuring data sovereignty.

---

## 3. High-Level Architecture

The system follows a modern **Clean Architecture** pattern:

### **Frontend (React)**
Builds the user interface using **Vite**, **Tailwind CSS**, and **Lucide Icons**. it handles:
*   Real-time chat interactions.
*   File uploads with progress tracking.
*   JWT-based authentication.

### **Backend (FastAPI)**
The core engine enabling the AI services:
*   **Ingestion Pipeline**: Splits documents into "chunks" and converts them to mathematical vectors.
*   **RAG Engine**: Retrieves relevant chunks and generates answers using the LLM.
*   **Middleware**: Handles Rate Limiting (Redis) and CORS security.

### **Data Storage**
*   **Oracle Database**: Stores user profiles, document metadata, and audit logs.
*   **Vector Store (Milvus/FAISS)**: Stores the high-dimensional vectors for similarity search.
*   **Redis**: Caches frequent answers and manages API rate limits.

*(For detailed architectural diagrams, refer to `SYSTEM_ARCHITECTURE.md`)*

---

## 4. Technology Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Language** | Python 3.12+ | Core backend logic. |
| **Framework** | FastAPI | High-performance Async Web API. |
| **Frontend** | React 18 | Interactive UI (Vite bundler). |
| **LLM** | Llama 3 / Ollama | Local inference engine. |
| **Database** | Oracle / PostgreSQL | Relational data storage. |
| **Vector DB** | Milvus / FAISS | Semantic search index. |
| **Caching** | Redis | Response caching & Rate limiting. |
| **Security** | OAuth2 / JWT | Stateless authentication. |

---

## 5. User Manual

### 5.1 Roles
*   **Admin**: Can view system stats, manage users, and see all documents.
*   **User**: Can upload documents to their department and chat with them.

### 5.2 How to Upload
1.  Navigate to the **Chat Interface**.
2.  Click the **"Upload Document"** button (Cloud Icon).
3.  Select your file (PDF, Excel, etc.) and assign a Title and Department.
4.  Wait for the status to change to `Ready` (Green Checkmark).

### 5.3 How to Chat
1.  Type your question in the message bar (e.g., *"What is the policy on remote work?"*).
2.  The AI will analyze the authorized documents and provide an answer.
3.  Click the **[1]** citations to view the source text.
4.  Use **"Edit"** to refine your last question or **"Regenerate"** to try a different answer.

### 5.4 Admin Dashboard
*   Access via the sidebar.
*   View system health, total documents indexed, and critical system logs.

---

## 6. Developer & Deployment Guide

For technical setup, installation, and production deployment instructions, please refer to:
*   **`INSTRUCTION.md`**: detailed production deployment steps.
*   **`SYSTEM_ARCHITECTURE.md`**: Deep dive into the codebase structure.
