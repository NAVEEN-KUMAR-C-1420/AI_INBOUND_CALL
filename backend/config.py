import os

CLIENT = "telecorp"  # change to "banking" to switch

BASE_DIR = os.path.dirname(__file__)
CLIENT_DIR = os.path.join(BASE_DIR, "clients", CLIENT)
KB_PATH = os.path.join(CLIENT_DIR, "kb.json")
CUSTOMERS_PATH = os.path.join(CLIENT_DIR, "customers.json")
DB_PATH = os.path.join(BASE_DIR, "telecom_ai.db")


def get_kb():
    import json
    with open(KB_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_client_id():
    return CLIENT

# === END OF FILE: config.py ===
