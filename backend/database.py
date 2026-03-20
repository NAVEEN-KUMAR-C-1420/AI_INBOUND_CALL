from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./telecom_ai.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    plan = Column(String(50), default="Basic")
    created_at = Column(DateTime, default=datetime.utcnow)

    calls = relationship("Call", back_populates="customer")
    memories = relationship("Memory", back_populates="customer")


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    status = Column(String(20), default="active")  # active, completed, abandoned

    customer = relationship("Customer", back_populates="calls")
    conversations = relationship("Conversation", back_populates="call")
    summary = relationship("Summary", back_populates="call", uselist=False)


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=False)
    speaker = Column(String(20), nullable=False)  # customer, ai
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    intent = Column(String(100), nullable=True)
    sentiment = Column(String(50), nullable=True)

    call = relationship("Call", back_populates="conversations")


class Memory(Base):
    __tablename__ = "memory"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    issue = Column(Text, nullable=False)
    status = Column(String(20), default="unresolved")  # resolved, unresolved
    sentiment = Column(String(50), nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    customer = relationship("Customer", back_populates="memories")


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    call_id = Column(Integer, ForeignKey("calls.id"), unique=True, nullable=False)
    summary = Column(Text, nullable=False)
    issue = Column(Text, nullable=True)
    sentiment = Column(String(50), nullable=True)
    resolved = Column(Boolean, default=False)
    action = Column(Text, nullable=True)
    compliance = Column(String(20), default="ok")  # ok, violation
    decision = Column(String(50), nullable=True)  # resolve, escalate
    created_at = Column(DateTime, default=datetime.utcnow)

    call = relationship("Call", back_populates="summary")


def init_db():
    Base.metadata.create_all(bind=engine)

    # Add sample customer if none exists
    db = SessionLocal()
    try:
        if db.query(Customer).count() == 0:
            sample_customers = [
                Customer(name="James Richardson", phone="+1234567890", plan="Premium"),
                Customer(name="Jane Smith", phone="+0987654321", plan="Basic"),
                Customer(name="Bob Wilson", phone="+1122334455", plan="Business"),
            ]
            db.add_all(sample_customers)
            db.commit()
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Multi-tenant functions using sqlite3 (for client-specific tables)
# =============================================================================
import json
import sqlite3
from typing import Optional, List
from config import DB_PATH, get_client_id


def get_customer_by_phone(phone: str) -> Optional[dict]:
    """Get customer by phone number from client-specific table."""
    client = get_client_id()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(
            f"SELECT * FROM {client}_customers WHERE phone = ? LIMIT 1",
            (phone,)
        )
        row = cursor.fetchone()

        if row:
            result = dict(row)
            # Parse raw JSON field and merge with row data
            if result.get("raw"):
                try:
                    raw_data = json.loads(result["raw"])
                    result.update(raw_data)
                except json.JSONDecodeError:
                    pass
            return result
        return None
    except Exception as e:
        print(f"Error getting customer by phone: {e}")
        return None
    finally:
        conn.close()


def get_customer_by_name(name: str) -> Optional[dict]:
    """Get customer by first/full name from client-specific table."""
    if not name:
        return None

    client = get_client_id()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    normalized = name.strip().lower()
    first_name = normalized.split()[0] if normalized else normalized

    try:
        cursor.execute(
            f"""
            SELECT *
            FROM {client}_customers
            WHERE lower(full_name) = ?
               OR lower(full_name) LIKE ?
            LIMIT 1
            """,
            (normalized, f"{first_name}%"),
        )
        row = cursor.fetchone()

        if row:
            result = dict(row)
            if result.get("raw"):
                try:
                    raw_data = json.loads(result["raw"])
                    result.update(raw_data)
                except json.JSONDecodeError:
                    pass
            return result
        return None
    except Exception as e:
        print(f"Error getting customer by name: {e}")
        return None
    finally:
        conn.close()


def get_customer_by_id(customer_id: str) -> Optional[dict]:
    """Get customer by ID from client-specific table."""
    client = get_client_id()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(
            f"SELECT * FROM {client}_customers WHERE id = ? LIMIT 1",
            (customer_id,)
        )
        row = cursor.fetchone()

        if row:
            result = dict(row)
            # Parse raw JSON field and merge with row data
            if result.get("raw"):
                try:
                    raw_data = json.loads(result["raw"])
                    result.update(raw_data)
                except json.JSONDecodeError:
                    pass
            return result
        return None
    except Exception as e:
        print(f"Error getting customer by ID: {e}")
        return None
    finally:
        conn.close()


def get_all_customers() -> List[dict]:
    """Get all customers from client-specific table."""
    client = get_client_id()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(f"""
            SELECT id, full_name, phone, plan_name, account_status,
                   churn_risk_score, outstanding_balance_gbp, tags, call_history_count
            FROM {client}_customers
            ORDER BY churn_risk_score DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"Error getting all customers: {e}")
        return []
    finally:
        conn.close()


def get_kb_for_intent(intent_id: str) -> str:
    """Get knowledge base answer for a specific intent."""
    client = get_client_id()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(
            f"SELECT answer FROM {client}_kb_entries WHERE intent_id = ? LIMIT 1",
            (intent_id,)
        )
        row = cursor.fetchone()

        if row:
            return row["answer"]
        return "Please hold while I check that for you."
    except Exception as e:
        print(f"Error getting KB for intent: {e}")
        return "Please hold while I check that for you."
    finally:
        conn.close()


def get_all_kb_context(limit: int = 10) -> str:
    """Get knowledge base context for AI prompt injection."""
    client = get_client_id()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute(f"""
            SELECT intent_id, question, answer
            FROM {client}_kb_entries
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()

        if not rows:
            return "No knowledge base entries available."

        result = []
        for idx, row in enumerate(rows, 1):
            result.append(
                f"{idx}. If customer says: {row['question']}\n"
                f"   Resolve by: {row['answer'][:200]}..."
            )

        return "\n\n".join(result)
    except Exception as e:
        print(f"Error getting KB context: {e}")
        return "Knowledge base temporarily unavailable."
    finally:
        conn.close()


def save_call_session(session: dict) -> None:
    """Save a call session to client-specific table."""
    client = get_client_id()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(f"""
            INSERT OR REPLACE INTO {client}_call_sessions (
                id, customer_id, call_type, call_mode, started_at, ended_at,
                duration_seconds, transcript, sentiment_arc, intent, resolution,
                summary, recording_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session.get("id"),
            session.get("customer_id"),
            session.get("call_type"),
            session.get("call_mode", "assisted"),
            session.get("started_at"),
            session.get("ended_at"),
            session.get("duration_seconds"),
            json.dumps(session.get("transcript")) if session.get("transcript") else None,
            json.dumps(session.get("sentiment_arc")) if session.get("sentiment_arc") else None,
            session.get("intent"),
            session.get("resolution"),
            session.get("summary"),
            session.get("recording_url")
        ))
        conn.commit()
    except Exception as e:
        print(f"Error saving call session: {e}")
    finally:
        conn.close()

# === END OF FILE: database.py additions ===
