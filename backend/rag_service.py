"""
RAG (Retrieval Augmented Generation) Service for AI Call Center.

This module handles:
  1. Setting up the selected vector database (Chroma, Pinecone, or SQLite memory)
  2. Embedding KB entries and indexing them in the vector DB at startup
  3. Querying the vector database using query embeddings at call time
  4. Building a focused, grounded prompt for the LLM
"""

# pyright: reportMissingImports=false

import sqlite3
import json
import os
import time
import importlib
from typing import List, Dict, Tuple, Optional, Any
import numpy as np
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================
# CONFIGURATION & GLOBAL STATE
# ============================================================
DB_PATH: str = os.path.join(os.path.dirname(__file__), "telecom_ai.db")

VECTOR_DB_PROVIDER = os.getenv("VECTOR_DB_PROVIDER", "sqlite").lower()

# Chroma Config
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(os.path.dirname(__file__), "chroma_db"))
CHROMA_SERVER_HOST = os.getenv("CHROMA_SERVER_HOST", "")
CHROMA_SERVER_PORT = os.getenv("CHROMA_SERVER_PORT", "8000")

# Pinecone Config
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "telecom-kb")

_embedder: Optional[Any] = None
_model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

# ============================================================
# EMBEDDING HELPER
# ============================================================
def load_embedder() -> Any:
    """Load the sentence transformer model lazily (only once)."""
    global _embedder
    if _embedder is not None:
        return _embedder

    try:
        sentence_transformers = importlib.import_module("sentence_transformers")
        model_cls = getattr(sentence_transformers, "SentenceTransformer")
        _embedder = model_cls(_model_name)
        print("RAG: embedding model loaded.")
        return _embedder
    except ImportError:
        print(f"ERROR: Failed to load embedding model. Run: pip install sentence-transformers")
        raise


def embed_text(text: str) -> np.ndarray:
    """Embed a string and return normalized float vector."""
    embedder = load_embedder()
    vector = embedder.encode([text], show_progress_bar=False)[0]
    # Normalize for cosine similarity
    vector = vector / np.linalg.norm(vector)
    return vector


# ============================================================
# VECTOR DATABASE ADAPTERS
# ============================================================
class BaseVectorStore:
    def initialize(self, client_id: str, kb_entries: List[Dict], embeddings: np.ndarray) -> None:
        raise NotImplementedError

    def search(self, query_vector: np.ndarray, top_k: int, min_score: float) -> List[Dict]:
        raise NotImplementedError


class SqliteVectorStore(BaseVectorStore):
    """Fallback local in-memory NumPy vector search."""
    def __init__(self):
        self.kb_vectors: Optional[np.ndarray] = None
        self.kb_entries: List[Dict] = []

    def initialize(self, client_id: str, kb_entries: List[Dict], embeddings: np.ndarray) -> None:
        self.kb_vectors = embeddings
        self.kb_entries = kb_entries
        print(f"RAG (SQLite/Memory): Loaded {len(kb_entries)} entries into local NumPy memory.")

    def search(self, query_vector: np.ndarray, top_k: int, min_score: float) -> List[Dict]:
        if self.kb_vectors is None or len(self.kb_entries) == 0:
            return []

        # Cosine similarity via dot product (vectors are normalized)
        scores = np.dot(self.kb_vectors, query_vector)
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score >= min_score:
                entry = dict(self.kb_entries[idx])
                entry["relevance_score"] = round(score, 3)
                results.append(entry)
        return results


class ChromaVectorStore(BaseVectorStore):
    """Chroma DB adapter supporting local persistent path or remote server."""
    def __init__(self):
        self.client = None
        self.collection = None

    def initialize(self, client_id: str, kb_entries: List[Dict], embeddings: np.ndarray) -> None:
        try:
            chromadb = importlib.import_module("chromadb")
        except ImportError:
            print("ERROR: chromadb is not installed. Please run: pip install chromadb")
            raise

        if CHROMA_SERVER_HOST:
            print(f"RAG (Chroma): Connecting to server at {CHROMA_SERVER_HOST}:{CHROMA_SERVER_PORT}...")
            self.client = chromadb.HttpClient(host=CHROMA_SERVER_HOST, port=CHROMA_SERVER_PORT)
        else:
            print(f"RAG (Chroma): Initializing persistent local DB at {CHROMA_DB_PATH}...")
            self.client = chromadb.PersistentClient(path=CHROMA_DB_PATH)

        collection_name = f"kb_{client_id}".replace("-", "_")
        # Delete if exists to refresh, or get/create
        try:
            self.client.delete_collection(name=collection_name)
        except Exception:
            pass

        self.collection = self.client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        ids = [str(entry["id"]) for entry in kb_entries]
        documents = [f"{entry.get('question', '')} {entry.get('answer', '')} {entry.get('keywords') or ''}" for entry in kb_entries]
        metadatas = []
        for entry in kb_entries:
            metadatas.append({
                "intent_id": entry.get("intent_id") or "",
                "category": entry.get("category") or "",
                "question": entry.get("question") or "",
                "answer": entry.get("answer") or "",
                "keywords": entry.get("keywords") or "",
            })

        # Chroma handles embeddings list conversion
        self.collection.add(
            ids=ids,
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=metadatas
        )
        print(f"RAG (Chroma): Successfully indexed {len(kb_entries)} entries in collection '{collection_name}'")

    def search(self, query_vector: np.ndarray, top_k: int, min_score: float) -> List[Dict]:
        if not self.collection:
            return []

        results = self.collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=top_k
        )

        search_results = []
        if not results or "ids" not in results or not results["ids"]:
            return []

        ids = results["ids"][0]
        distances = results["distances"][0] if "distances" in results else [0.0] * len(ids)
        metadatas = results["metadatas"][0] if "metadatas" in results else [{}] * len(ids)

        for i in range(len(ids)):
            # Cosine similarity score = 1 - cosine distance (depending on Chroma configuration)
            # In Chroma with space 'cosine', distance is 1 - similarity. So similarity is 1 - distance.
            score = 1.0 - float(distances[i])
            if score >= min_score:
                meta = metadatas[i]
                search_results.append({
                    "id": ids[i],
                    "intent_id": meta.get("intent_id"),
                    "category": meta.get("category"),
                    "question": meta.get("question"),
                    "answer": meta.get("answer"),
                    "keywords": meta.get("keywords"),
                    "relevance_score": round(score, 3)
                })
        return search_results


class PineconeVectorStore(BaseVectorStore):
    """Pinecone DB adapter for cloud-based deployment."""
    def __init__(self):
        self.index = None

    def initialize(self, client_id: str, kb_entries: List[Dict], embeddings: np.ndarray) -> None:
        if not PINECONE_API_KEY or not PINECONE_INDEX_NAME:
            raise ValueError("PINECONE_API_KEY and PINECONE_INDEX_NAME must be set in .env for Pinecone provider.")

        try:
            pinecone = importlib.import_module("pinecone")
            Pinecone = getattr(pinecone, "Pinecone")
        except ImportError:
            print("ERROR: pinecone-client is not installed. Please run: pip install pinecone-client")
            raise

        pc = Pinecone(api_key=PINECONE_API_KEY)
        print(f"RAG (Pinecone): Connecting to index '{PINECONE_INDEX_NAME}'...")
        self.index = pc.Index(PINECONE_INDEX_NAME)

        # Upsert in batches
        vectors_to_upsert = []
        for i, entry in enumerate(kb_entries):
            metadata = {
                "client_id": client_id,
                "intent_id": entry.get("intent_id") or "",
                "category": entry.get("category") or "",
                "question": entry.get("question") or "",
                "answer": entry.get("answer") or "",
                "keywords": entry.get("keywords") or "",
            }
            vectors_to_upsert.append((
                str(entry["id"]),
                embeddings[i].tolist(),
                metadata
            ))

        # Chunk upserts to prevent payload limit overflow
        chunk_size = 100
        for i in range(0, len(vectors_to_upsert), chunk_size):
            chunk = vectors_to_upsert[i:i + chunk_size]
            self.index.upsert(vectors=chunk)

        print(f"RAG (Pinecone): Upserted {len(kb_entries)} vector embeddings.")

    def search(self, query_vector: np.ndarray, top_k: int, min_score: float) -> List[Dict]:
        if not self.index:
            return []

        response = self.index.query(
            vector=query_vector.tolist(),
            top_k=top_k,
            include_metadata=True
        )

        results = []
        for match in response.get("matches", []):
            score = float(match.get("score", 0.0))
            if score >= min_score:
                meta = match.get("metadata", {})
                results.append({
                    "id": match.get("id"),
                    "intent_id": meta.get("intent_id"),
                    "category": meta.get("category"),
                    "question": meta.get("question"),
                    "answer": meta.get("answer"),
                    "keywords": meta.get("keywords"),
                    "relevance_score": round(score, 3)
                })
        return results


# ============================================================
# ACTIVE VECTOR STORE INSTANCE SELECTOR
# ============================================================
_vector_store: BaseVectorStore = SqliteVectorStore()

if VECTOR_DB_PROVIDER == "chroma":
    _vector_store = ChromaVectorStore()
elif VECTOR_DB_PROVIDER == "pinecone":
    _vector_store = PineconeVectorStore()
else:
    _vector_store = SqliteVectorStore()


# ============================================================
# PUBLIC INTERFACE METHODS
# ============================================================
def load_kb_into_memory(client_id: str = "telecorp") -> int:
    """
    Load all KB entries for a client from the database, pre-compute
    embeddings, and initialize the active Vector Store provider.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        table_name = f"{client_id}_kb_entries"

        # Check if table exists
        cursor.execute(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
        )
        if not cursor.fetchone():
            print(f"RAG: Warning — table {table_name} not found. Run seed.py first.")
            conn.close()
            return 0

        # Fetch all KB entries
        cursor.execute(
            f"""
            SELECT id, intent_id, category, question, answer,
                   sample_phrases, keywords
            FROM {table_name}
            ORDER BY intent_id
            """
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            print(f"RAG: Warning — no KB entries found in {table_name}")
            return 0

        searchable_texts = []
        kb_entries_list = []

        for row in rows:
            entry_dict = dict(row)
            kb_entries_list.append(entry_dict)

            # Combine question, answer, and keywords for richer embedding
            question = entry_dict.get("question", "")
            answer = entry_dict.get("answer", "")
            keywords = entry_dict.get("keywords") or ""
            searchable = f"{question} {answer} {keywords}"
            searchable_texts.append(searchable)

        # Load embedding model and encode all texts
        embedder = load_embedder()
        print(f"RAG: encoding {len(searchable_texts)} KB entries using {VECTOR_DB_PROVIDER}...")
        vectors = embedder.encode(
            searchable_texts, batch_size=32, show_progress_bar=False
        )

        # Normalize vectors for cosine similarity
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

        # Initialize selected Vector Database Store
        _vector_store.initialize(client_id, kb_entries_list, vectors)

        return len(kb_entries_list)

    except Exception as e:
        print(f"RAG: Error loading and indexing KB: {e}")
        # Fallback to local numpy implementation if initialization fails
        print("RAG: Falling back to Local SQLite Memory storage...")
        fallback_store = SqliteVectorStore()
        try:
            fallback_store.initialize(client_id, kb_entries_list, vectors)
            globals()["_vector_store"] = fallback_store
            return len(kb_entries_list)
        except Exception:
            return 0


def retrieve_kb(query: str, top_k: int = 3, min_score: float = 0.25) -> List[Dict]:
    """
    Retrieve top_k most relevant KB entries using the active Vector Database.
    """
    try:
        query_vec = embed_text(query)
        return _vector_store.search(query_vec, top_k, min_score)
    except Exception as e:
        print(f"RAG: Query search failed: {e}")
        return []


def build_rag_prompt(
    customer_message: str,
    customer: Optional[Dict],
    conversation_history: List[Dict],
    client_id: str = "telecorp",
) -> Tuple[str, List[Dict]]:
    """
    Build the complete, grounded prompt for the LLM using RAG results.
    Returns (prompt_string, retrieved_kb_entries)
    """
    # A. Retrieve relevant KB entries
    retrieved = retrieve_kb(customer_message, top_k=3)

    # B. Build KB context block
    kb_context = ""
    if retrieved:
        for entry in retrieved:
            intent_id = entry.get("intent_id", "unknown")
            answer = entry.get("answer", "")
            kb_context += f"Resolution for '{intent_id}':\n{answer}\n\n"
    else:
        kb_context = "No specific resolution found. Use general best practices."

    # C. Build detailed customer context block
    if customer:
        full_name = customer.get("full_name", "Unknown")
        phone = customer.get("phone", "Unknown")
        email = customer.get("email", "Unknown")
        plan_name = customer.get("plan_name", "Unknown")
        monthly_fee = customer.get("monthly_fee_gbp", 0)
        outstanding = customer.get("outstanding_balance_gbp", 0)
        account_status = customer.get("account_status", "active")
        call_count = customer.get("call_history_count", 0)
        last_intent = customer.get("last_call_intent", "None")
        last_resolved = customer.get("last_call_resolved", True)
        repeat_issue = customer.get("repeat_issue", False)
        churn_risk = customer.get("churn_risk_score", 0.0)

        customer_block = f"""
IMPORTANT — YOU ALREADY HAVE THIS CUSTOMER'S DETAILS. DO NOT ASK FOR THEM AGAIN.

Customer name:     {full_name}
Phone:             {phone}
Email:             {email}
Plan:              {plan_name} at £{monthly_fee}/month
Outstanding:       £{outstanding}
Account status:    {account_status}
Previous calls:    {call_count}
Last issue:        {last_intent}
Issue resolved:    {'No — follow up needed' if last_resolved == 0 else 'Yes'}
Repeat caller:     {'YES — apologise immediately' if repeat_issue else 'No'}
Churn risk:        {'HIGH — offer retention deal' if float(churn_risk) > 0.6 else 'Normal'}

RULES BASED ON THIS CUSTOMER:
- Do NOT ask for their name, phone, email or address — you already have them above
- Do NOT ask to verify their identity again — they are already verified
- If repeat_issue is YES: acknowledge they have called before, apologise, prioritise the fix
- If outstanding balance > 0: mention naturally and offer a payment plan
- If churn_risk is HIGH: offer retention incentive (discount/upgrade) before call ends
- Use their first name naturally throughout the call
"""
    else:
        customer_block = """
Unknown caller — no account found.
Ask for their full name and a one-line summary of their issue first, then look them up.
Do NOT ask for address, age or email until the first lookup attempt is done.
"""

    # D. Build recent conversation (last 4 turns only)
    history_lines = []
    for msg in conversation_history[-4:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        prefix = "Customer" if role == "user" else "Sarah"
        history_lines.append(f"{prefix}: {content}")

    history_text = "\n".join(history_lines)

    # E. Build final prompt
    prompt = f"""You are Sarah, TeleCorp UK customer service. Professional and empathetic.

CUSTOMER: {customer_block}

RELEVANT KNOWLEDGE BASE:
{kb_context}

CONVERSATION:
{history_text}
Customer: {customer_message}

Sarah (2-3 sentences, specific, no apologies for delays):"""

    return (prompt, retrieved)


def get_rag_context_for_display(query: str, top_k: int = 3) -> List[Dict]:
    """
    Returns RAG results formatted for the frontend intelligence panel.
    Each result has: intent_id, relevance_score, answer_preview
    """
    results = retrieve_kb(query, top_k=top_k)

    display_results = []
    for result in results:
        intent_id = result.get("intent_id", "unknown")
        relevance_score = result.get("relevance_score", 0)
        answer = result.get("answer", "")

        # Preview: first 80 characters + "..."
        answer_preview = (answer[:80] + "...") if len(answer) > 80 else answer

        display_results.append({
            "intent_id": intent_id,
            "relevance_score": relevance_score,
            "answer_preview": answer_preview,
        })

    return display_results


def warmup_rag(client_id: str = "telecorp") -> bool:
    """
    Called at FastAPI startup.
    Returns True if RAG is ready, False otherwise.
    """
    try:
        n = load_kb_into_memory(client_id)
        if n == 0:
            print("RAG: No KB entries loaded. Check seed.py has been run.")
            return False

        # Test with dummy query
        results = retrieve_kb("billing problem", top_k=1)
        if results:
            print(f"RAG System Warmup Succeeded using provider '{VECTOR_DB_PROVIDER}'.")
            return True
        else:
            print("RAG: Loaded but returned no results. Check seed.py has been run.")
            return False
    except Exception as e:
        print(f"RAG: Error during warmup: {e}")
        return False


# ============================================================
# TEST SCRIPT
# ============================================================
if __name__ == "__main__":
    print(f"=== Testing RAG Service with provider: {VECTOR_DB_PROVIDER} ===\n")

    # Force SQLite/numpy for test script run if dependencies aren't ready
    n = load_kb_into_memory("telecorp")
    print(f"Loaded {n} entries\n")

    test_queries = [
        "why was I charged twice",
        "no signal at home",
        "I want to cancel and switch to BT",
    ]

    for q in test_queries:
        results = retrieve_kb(q, top_k=2)
        print(f"Query: '{q}'")
        if results:
            for r in results:
                intent = r.get("intent_id", "unknown")
                score = r.get("relevance_score", 0)
                answer_preview = r.get("answer", "")[:80]
                print(f"  -> {intent} (score: {score})")
                print(f"     {answer_preview}...")
        else:
            print("  -> No results found")
        print()
