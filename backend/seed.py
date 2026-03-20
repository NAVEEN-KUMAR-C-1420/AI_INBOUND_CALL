#!/usr/bin/env python3
"""
Seed script for multi-tenant AI Call Center database.
Usage:
    python seed.py                    # Seed all clients
    python seed.py --client telecorp  # Seed telecorp only
    python seed.py --client banking   # Seed banking only
    python seed.py --reset            # Reset and reseed all
    python seed.py --verify           # Verify row counts
"""

import sqlite3
import json
import os
import sys
import argparse

# Import from config
from config import DB_PATH, BASE_DIR


def get_conn() -> sqlite3.Connection:
    """Open database connection with Row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(client_id: str) -> None:
    """Create tables for a specific client if they don't exist."""
    conn = get_conn()
    cursor = conn.cursor()

    # Customers table
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {client_id}_customers (
            id TEXT PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            email TEXT,
            plan_name TEXT,
            monthly_fee_gbp REAL,
            outstanding_balance_gbp REAL DEFAULT 0,
            account_status TEXT DEFAULT 'active',
            account_type TEXT,
            churn_risk_score REAL DEFAULT 0.1,
            upsell_score REAL DEFAULT 0.5,
            call_history_count INTEGER DEFAULT 0,
            last_call_date TEXT,
            last_call_intent TEXT,
            last_call_resolved INTEGER,
            repeat_issue INTEGER DEFAULT 0,
            tags TEXT,
            flags TEXT,
            raw TEXT
        )
    """)

    # Call sessions table
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {client_id}_call_sessions (
            id TEXT PRIMARY KEY,
            customer_id TEXT,
            call_type TEXT,
            call_mode TEXT DEFAULT 'assisted',
            started_at TEXT,
            ended_at TEXT,
            duration_seconds INTEGER,
            transcript TEXT,
            sentiment_arc TEXT,
            intent TEXT,
            resolution TEXT,
            summary TEXT,
            embedding TEXT,
            recording_url TEXT
        )
    """)

    # KB entries table
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {client_id}_kb_entries (
            id TEXT PRIMARY KEY,
            category TEXT,
            intent_id TEXT,
            question TEXT,
            answer TEXT,
            resolution_rate REAL DEFAULT 0.8,
            sample_phrases TEXT,
            keywords TEXT
        )
    """)

    conn.commit()
    conn.close()


def seed_customers(client_id: str) -> int:
    """Seed customers from JSON file."""
    customers_path = os.path.join(BASE_DIR, "clients", client_id, "customers.json")

    if not os.path.exists(customers_path):
        print(f"  Warning: {customers_path} not found")
        return 0

    with open(customers_path, encoding="utf-8") as f:
        customers = json.load(f)

    conn = get_conn()
    cursor = conn.cursor()
    count = 0

    for c in customers:
        try:
            cursor.execute(f"""
                INSERT OR REPLACE INTO {client_id}_customers (
                    id, full_name, phone, email, plan_name, monthly_fee_gbp,
                    outstanding_balance_gbp, account_status, account_type,
                    churn_risk_score, upsell_score, call_history_count,
                    last_call_date, last_call_intent, last_call_resolved,
                    repeat_issue, tags, flags, raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                c.get("id"),
                c.get("full_name"),
                c.get("phone"),
                c.get("email"),
                c.get("plan_name") or c.get("account_type"),
                c.get("monthly_fee_gbp") or 0,
                c.get("outstanding_balance_gbp") or 0,
                c.get("account_status", "active"),
                c.get("account_type"),
                c.get("churn_risk_score") or 0.1,
                c.get("upsell_score") or 0.5,
                c.get("call_history_count") or 0,
                c.get("last_call_date"),
                c.get("last_call_intent"),
                1 if c.get("last_call_resolved") else 0,
                1 if c.get("repeat_issue") else 0,
                json.dumps(c.get("tags") or c.get("flags") or []),
                json.dumps(c.get("flags") or []),
                json.dumps(c)
            ))
            count += 1
        except Exception as e:
            print(f"  Error inserting customer {c.get('id')}: {e}")

    conn.commit()
    conn.close()
    return count


def seed_kb(client_id: str) -> int:
    """Seed knowledge base entries from kb.json."""
    kb_path = os.path.join(BASE_DIR, "clients", client_id, "kb.json")

    if not os.path.exists(kb_path):
        print(f"  Warning: {kb_path} not found")
        return 0

    with open(kb_path, encoding="utf-8") as f:
        kb = json.load(f)

    intents = kb.get("intents", [])

    conn = get_conn()
    cursor = conn.cursor()
    count = 0

    for intent in intents:
        intent_id = intent.get("id")
        category = intent.get("category") or intent_id
        sample_phrases = intent.get("sample_customer_phrases") or []
        resolution_steps = intent.get("resolution_steps") or []
        answer = "\n".join(resolution_steps)
        keywords = intent.get("keywords") or []
        auto_resolvable = intent.get("auto_resolvable", False)
        resolution_rate = 0.9 if auto_resolvable else 0.75

        for idx, phrase in enumerate(sample_phrases):
            try:
                entry_id = f"{intent_id}_{idx}"
                cursor.execute(f"""
                    INSERT OR REPLACE INTO {client_id}_kb_entries (
                        id, category, intent_id, question, answer,
                        resolution_rate, sample_phrases, keywords
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    entry_id,
                    category,
                    intent_id,
                    phrase,
                    answer,
                    resolution_rate,
                    json.dumps(sample_phrases),
                    json.dumps(keywords)
                ))
                count += 1
            except Exception as e:
                print(f"  Error inserting KB entry {entry_id}: {e}")

    conn.commit()
    conn.close()
    return count


def seed_client(client_id: str) -> None:
    """Seed all data for a specific client."""
    print(f"\n[{client_id}] Seeding database...")

    create_tables(client_id)
    cust_count = seed_customers(client_id)
    kb_count = seed_kb(client_id)

    print(f"[{client_id}] {cust_count} customers, {kb_count} KB entries seeded into {DB_PATH}")


def reset_client(client_id: str) -> None:
    """Drop and recreate tables for a specific client."""
    print(f"\n[{client_id}] Resetting tables...")

    conn = get_conn()
    cursor = conn.cursor()

    # Drop existing tables
    tables = [
        f"{client_id}_customers",
        f"{client_id}_call_sessions",
        f"{client_id}_kb_entries"
    ]

    for table in tables:
        try:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception as e:
            print(f"  Warning dropping {table}: {e}")

    conn.commit()
    conn.close()

    # Reseed
    seed_client(client_id)
    print(f"[{client_id}] Reset complete.")


def verify(client_id: str) -> None:
    """Verify row counts for a specific client."""
    print(f"\n[{client_id}] Verification:")
    print("-" * 50)

    conn = get_conn()
    cursor = conn.cursor()

    tables = [
        f"{client_id}_customers",
        f"{client_id}_call_sessions",
        f"{client_id}_kb_entries"
    ]

    for table in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {table}: {count} rows")
        except Exception as e:
            print(f"  {table}: ERROR - {e}")

    # Sample customers
    print(f"\n[{client_id}] Sample customers:")
    try:
        cursor.execute(f"""
            SELECT full_name, tags FROM {client_id}_customers LIMIT 3
        """)
        rows = cursor.fetchall()
        for row in rows:
            print(f"  - {row['full_name']}: {row['tags']}")
    except Exception as e:
        print(f"  Error fetching samples: {e}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Seed multi-tenant AI Call Center database")
    parser.add_argument(
        "--client",
        default="all",
        choices=["all", "telecorp", "banking"],
        help="Which client to seed (default: all)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate tables before seeding"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify row counts instead of seeding"
    )

    args = parser.parse_args()

    # Determine which clients to process
    if args.client == "all":
        clients_to_run = ["telecorp", "banking"]
    else:
        clients_to_run = [args.client]

    # Execute for each client
    for client in clients_to_run:
        if args.reset:
            reset_client(client)
        elif args.verify:
            verify(client)
        else:
            seed_client(client)

    print("\nDone. Run 'python seed.py --verify' to check row counts.")


if __name__ == "__main__":
    main()

# === END OF FILE: seed.py ===
