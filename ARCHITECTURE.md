# Project Architecture and Detailed Working Flow

This document explains the architecture, components, database scheme, RAG workflow, and runtime execution of the Telecom AI Call System.

---

## 1. High-Level Architecture Overview

The application follows a standard client-server model optimized for real-time speech and simulation:

```
                  ┌────────────────────────────────────────┐
                  │          Frontend (React + TS)         │
                  │   - Live Inbound Call UI               │
                  │   - Web Speech API (STT & TTS)         │
                  │   - Real-Time Intelligence dashboard   │
                  └───────────┬────────────────┬───────────┘
                              │                ▲
               WebSockets /   │ REST           │ Live Status/
               HTTP Requests  │ Endpoints      │ Intelligence
                              ▼                │
                  ┌────────────────────────────┴───────────┐
                  │           Backend (FastAPI)            │
                  │   - Inbound Call Simulation            │
                  │   - Real-time LLM router               │
                  │   - Memory & Context service           │
                  └───────────┬──────────────┬─────────────┘
                              │              │
           Vector Embeddings  │              │ SQL Records
                              ▼              ▼
                  ┌───────────┴────┐   ┌─────┴─────────────┐
                  │ Vector Store   │   │ SQLite Database   │
                  │ (Pinecone /    │   │ (telecom_ai.db)   │
                  │  Chroma DB /   │   │ - Customers & Call│
                  │  In-Memory SQL)│   │   History         │
                  └────────────────┘   └───────────────────┘
```

---

## 2. Core Components

### A. Frontend (React + TypeScript)
- **Speech-to-Text (STT):** Uses the browser's native Web Speech API (`webkitSpeechRecognition`) to capture mic inputs and stream them into text.
- **Text-to-Speech (TTS):** Uses the browser's native `SpeechSynthesis` to read the generated AI agent replies out loud.
- **Intelligence Dashboard:** Displays live variables such as sentiment (Neutral/Angry/Frustrated), call category/intent (billing, network, plan change), and urgency level (Low/Medium/High) along with RAG context snippets.

### B. Backend (FastAPI + Python)
- **LLM Service (`llm_service.py`):** Integrates multiple LLM providers (Ollama, Gemini, Groq, Together, and OpenRouter). Orchestrates conversational prompts.
- **RAG Service (`rag_service.py`):** Encapsulates the vector search logic, embedding indexing, and prompt generation.
- **Memory Service (`memory_service.py`):** Manages persistent memory records of customers, tracking recurring problems and past resolutions.
- **SQLite Database (`database.py`):** Standard relational tables for logging customers, call logs, conversations, and post-call summaries.

---

## 3. Database Schema & Multi-Tenancy

The project supports multi-tenancy configurations (e.g. `banking` or `telecorp` set via `CLIENT` in `config.py`). Tables in the SQLite file `telecom_ai.db` include:

1. **`customers` / `<client>_customers`:** Stores customer profile data (name, phone, plan, email, outstanding balance).
2. **`calls`:** Tracks starting time, ending time, status (active, completed).
3. **`conversations`:** Logs individual message turns between customers and agents, with recognized intent and sentiment.
4. **`memory`:** Logs persistent issues across call history for active follow-ups.
5. **`summaries`:** Stores AI-generated post-call summary details including compliance violations and resolution state.

---

## 4. Vector Database & RAG System Workflow

The retrieval-augmented generation (RAG) system grounds LLM prompts using relevant entries from a client-specific Knowledge Base (KB).

### Step 1: Initialization (`warmup_rag`)
When the FastAPI backend starts, `warmup_rag` runs:
1. Loads the SentenceTransformer embedding model (default: `all-MiniLM-L6-v2`, 384 dimensions).
2. Queries the SQL database for the active client's KB entries (e.g., `telecorp_kb_entries`).
3. Embeds each entry's question, answer, and keywords into a vector.
4. Uploads/synchronizes these embeddings into the selected `VECTOR_DB_PROVIDER` (`pinecone`, `chroma`, or `sqlite`).

### Step 2: Where are the Embeddings Stored?
- **Pinecone (`pinecone`):** Uploaded to cloud-based indexes hosted on Pinecone's server. Requires `PINECONE_API_KEY` and `PINECONE_INDEX_NAME`.
- **Chroma DB (`chroma`):** Persisted locally inside the workspace folder `backend/chroma_db` (using `PersistentClient`), or sent to a local/remote Chroma Server if configured.
- **SQLite In-Memory (`sqlite`):** Kept as a normalized `numpy` array matrix in memory (`_kb_vectors`) during server runtime. Used as a safe zero-dependency fallback if cloud/local DB connections fail.

### Step 3: Retrieval during live calls
When the customer speaks:
1. The text is transcribed and sent to the `/api/chat` backend endpoint.
2. The user's query is embedded.
3. The vector database computes cosine similarity and returns the top-K relevant KB entries.
4. The system combines:
   - Customer profile details
   - Active system state (postcode, identity verification)
   - Recent conversation history
   - Retrieved RAG knowledge base resolutions
5. A structured prompt is compiled and dispatched to the LLM to generate a contextually accurate response.
