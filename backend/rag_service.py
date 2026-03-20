"""
RAG (Retrieval Augmented Generation) Service for AI Call Center.

This module handles:
  1. Embedding KB entries at startup
  2. Embedding customer queries at call time
  3. Retrieving top-K most relevant KB entries
  4. Building a focused, grounded prompt for Ollama
"""

# pyright: reportMissingImports=false

import sqlite3
import json
import os
import time
import importlib
from typing import List, Dict, Tuple, Optional, Any

import numpy as np

# ============================================================
# GLOBAL STATE (module-level, loaded once at startup)
# ============================================================

_embedder: Optional[Any] = None
_kb_vectors: Optional[np.ndarray] = None  # shape: (N, 384)
_kb_entries: List[Dict] = []  # the raw KB rows
_model_name: str = "all-MiniLM-L6-v2"

# Construct DB path relative to this module
DB_PATH: str = os.path.join(os.path.dirname(__file__), "telecom_ai.db")


# ============================================================
# FUNCTION 1: load_embedder() -> SentenceTransformer
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


# ============================================================
# FUNCTION 2: load_kb_into_memory(client_id: str = "telecorp") -> int
# ============================================================
def load_kb_into_memory(client_id: str = "telecorp") -> int:
    """
    Load all KB entries for a client from the database into memory
    and pre-compute their embeddings as a numpy matrix.
    """
    global _kb_vectors, _kb_entries

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

        # Build searchable strings (question + answer + keywords)
        searchable_texts = []
        kb_entries_list = []

        for row in rows:
            # Convert sqlite3.Row to dict
            entry_dict = dict(row)
            kb_entries_list.append(entry_dict)

            # Combine question, answer, and keywords for richer embedding
            question = entry_dict.get("question", "")
            answer = entry_dict.get("answer", "")
            keywords = entry_dict.get("keywords") or ""

            searchable = f"{question} {answer} {keywords}"
            searchable_texts.append(searchable)

        # Load embedder and encode all texts
        embedder = load_embedder()
        print(f"RAG: encoding {len(searchable_texts)} KB entries...")
        vectors = embedder.encode(
            searchable_texts, batch_size=32, show_progress_bar=False
        )

        # Normalise each row for cosine similarity via dot product
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

        # Assign to globals
        _kb_vectors = vectors
        _kb_entries = kb_entries_list

        print(f"RAG: {len(kb_entries_list)} KB entries embedded for {client_id}")
        return len(kb_entries_list)

    except Exception as e:
        print(f"RAG: Error loading KB: {e}")
        return 0


# ============================================================
# FUNCTION 3: embed_query(text: str) -> np.ndarray
# ============================================================
def embed_query(text: str) -> np.ndarray:
    """
    Embed a single query string and return normalised 384-dim vector.
    """
    embedder = load_embedder()
    vector = embedder.encode([text], show_progress_bar=False)[0]

    # Normalise
    vector = vector / np.linalg.norm(vector)

    return vector


# ============================================================
# FUNCTION 4: retrieve_kb(
#     query: str,
#     top_k: int = 3,
#     min_score: float = 0.25
# ) -> List[Dict]
# ============================================================
def retrieve_kb(
    query: str, top_k: int = 3, min_score: float = 0.25
) -> List[Dict]:
    """
    Core RAG retrieval: find the top_k most relevant KB entries
    using cosine similarity.
    """
    if _kb_vectors is None or len(_kb_entries) == 0:
        return []

    # Embed query
    query_vec = embed_query(query)

    # Compute cosine similarities
    scores = np.dot(_kb_vectors, query_vec)

    # Get top indices
    top_indices = np.argsort(scores)[::-1][:top_k]

    # Build results
    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score >= min_score:
            entry = dict(_kb_entries[idx])
            entry["relevance_score"] = round(score, 3)
            results.append(entry)

    return results


# ============================================================
# FUNCTION 5: build_rag_prompt(
#     customer_message: str,
#     customer: Optional[Dict],
#     conversation_history: List[Dict],
#     client_id: str = "telecorp"
# ) -> Tuple[str, List[Dict]]
# ============================================================
def build_rag_prompt(
    customer_message: str,
    customer: Optional[Dict],
    conversation_history: List[Dict],
    client_id: str = "telecorp",
) -> Tuple[str, List[Dict]]:
    """
    Build the complete, grounded prompt for Ollama using RAG results.
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

    # C. Build detailed customer context block (CRITICAL FOR AVOIDING REPEATED QUESTIONS)
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

    # F. Return prompt and retrieved entries
    return (prompt, retrieved)


# ============================================================
# FUNCTION 6: get_rag_context_for_display(
#     query: str,
#     top_k: int = 3
# ) -> List[Dict]
# ============================================================
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


# ============================================================
# FUNCTION 7: warmup_rag(client_id: str = "telecorp") -> bool
# ============================================================
def warmup_rag(client_id: str = "telecorp") -> bool:
    """
    Called at FastAPI startup.
    Returns True if RAG is ready, False otherwise.
    """
    try:
        # Load KB into memory
        n = load_kb_into_memory(client_id)

        if n == 0:
            print("RAG: No KB entries loaded. Check seed.py has been run.")
            return False

        # Test with dummy query
        results = retrieve_kb("billing problem", top_k=1)

        if results:
            print("RAG: Ready.")
            return True
        else:
            print(
                "RAG: Loaded but returned no results. Check seed.py has been run."
            )
            return False

    except Exception as e:
        print(f"RAG: Error during warmup: {e}")
        return False


# ============================================================
# TEST SCRIPT
# ============================================================
if __name__ == "__main__":
    print("=== Testing RAG Service ===\n")

    n = load_kb_into_memory("telecorp")
    print(f"Loaded {n} entries\n")

    test_queries = [
        "why was I charged twice",
        "no signal at home",
        "I want to cancel and switch to BT",
        "my router keeps disconnecting",
        "I can't afford my bill this month",
        "I lost my SIM card",
        "I want to upgrade to unlimited data",
        "when does my contract end",
    ]

    for q in test_queries:
        results = retrieve_kb(q, top_k=2)
        print(f"Query: '{q}'")
        if results:
            for r in results:
                intent = r.get("intent_id", "unknown")
                score = r.get("relevance_score", 0)
                answer_preview = r.get("answer", "")[:80]
                print(f"  → {intent} (score: {score})")
                print(f"     {answer_preview}...")
        else:
            print("  → No results found")
        print()
