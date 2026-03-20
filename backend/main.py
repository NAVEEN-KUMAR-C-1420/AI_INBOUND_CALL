from datetime import datetime, timedelta
import asyncio
import uuid
from typing import Any, List, Optional, cast
from collections import deque
import re

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (
    Call,
    Conversation,
    Customer,
    Memory,
    Summary,
    get_all_customers,
    get_customer_by_id,
    get_customer_by_phone,
    get_db,
    init_db,
    save_call_session,
)
from language_service import (
    detect_language,
    get_response_language,
    get_system_prompt_language_instruction,
)
from sentiment_service import (
    detect_sentiment as detect_sentiment_ml,
    get_de_escalation_suggestion,
    get_sentiment_arc,
    urgency_level,
)
from outbound_service import (
    end_outbound_call,
    process_customer_response as process_outbound_response,
    start_outbound_call as start_outbound,
)
from memory_service import (
    cleanup_old_memories,
    end_call_memory,
    get_customer_pattern,
    get_customer_summary,
    get_or_create_memory,
)
from simulation_service import (
    end_simulation,
    get_available_scripts,
    get_next_sim_turn,
    get_sim_session,
    start_simulation as start_sim,
)
from abusive_words import detect_abusive_language
from ollama_service import (
    check_ollama_status,
    generate_call_summary,
    get_contextual_ai_response,
    get_ai_response,
)
from config import get_client_id
from temp_db_service import (
    append_turn as temp_append_turn,
    cleanup_temp_cache,
    end_call_cache,
    get_call_cache,
    get_phone_cache,
    hydrate_call_cache,
    refresh_phone_cache_from_call,
)

CALL_CONTEXT: dict[int, dict[str, Any]] = {}
CHAT_SESSION_CONTEXT: dict[str, dict[str, Any]] = {}


def _is_postcode(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    # Accept common UK-style and numeric pin/zip-like patterns.
    uk_pattern = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}\b", re.IGNORECASE)
    generic_pattern = re.compile(r"\b\d{5,6}\b")
    return bool(uk_pattern.search(t) or generic_pattern.search(t))


def _new_context(customer_profile: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    known_customer = bool(
        customer_profile
        and (
            customer_profile.get("name")
            or customer_profile.get("phone")
            or customer_profile.get("id")
        )
    )
    return {
        "history": deque(maxlen=5),
        "state": {
            "postcode_requested": False,
            "postcode_received": False,
            "issue_identified": False,
            "known_customer": known_customer,
            "verification_complete": known_customer,
        },
        "customer_profile": customer_profile or {},
    }


def _append_history(context: dict[str, Any], speaker: str, message: str) -> None:
    context["history"].append(f"{speaker}: {message}")


def _update_state_from_user(context: dict[str, Any], user_text: str, intent: str) -> None:
    state = context["state"]
    if _is_postcode(user_text):
        state["postcode_received"] = True
    if intent and intent not in ["other", "greeting", "account_query"]:
        state["issue_identified"] = True


def _update_state_from_ai(context: dict[str, Any], ai_text: str) -> None:
    state = context["state"]
    if "postcode" in (ai_text or "").lower() and not state.get("postcode_received"):
        state["postcode_requested"] = True


def _memory_lines(memories: List[Memory]) -> List[str]:
    return [f"- {m.issue} ({m.status})" for m in memories[:3]]


def _enrich_customer_profile(base_profile: dict[str, Any]) -> dict[str, Any]:
    """Merge fast SQL-call profile with richer tenant customer data by phone."""
    merged = dict(base_profile or {})
    phone = str(merged.get("phone") or "").strip()
    if not phone:
        return merged

    tenant_customer = get_customer_by_phone(phone)
    if not tenant_customer:
        return merged

    if tenant_customer.get("full_name") and not merged.get("name"):
        merged["name"] = tenant_customer.get("full_name")
    if tenant_customer.get("plan_name") and not merged.get("plan"):
        merged["plan"] = tenant_customer.get("plan_name")

    for key in [
        "id",
        "full_name",
        "email",
        "account_status",
        "account_type",
        "account_number",
        "sort_code",
        "balance_gbp",
        "outstanding_balance_gbp",
        "overdraft_limit_gbp",
        "loan",
        "card",
        "products_held",
        "language_preference",
        "plan_name",
        "monthly_fee_gbp",
        "last_bill_gbp",
        "payment_method",
        "autopay_enabled",
        "data_usage_percent",
        "contract_end",
        "churn_risk_score",
        "repeat_issue",
        "last_call_intent",
        "tags",
        "preferred_contact",
    ]:
        if key in tenant_customer and tenant_customer.get(key) is not None:
            merged[key] = tenant_customer.get(key)

    return merged


def _direct_db_response(user_text: str, customer_profile: dict[str, Any]) -> Optional[dict[str, str]]:
    """Return deterministic response for simple direct database questions."""
    t = (user_text or "").lower()
    if not customer_profile:
        return None

    name = str(
        customer_profile.get("name")
        or customer_profile.get("full_name")
        or "Customer"
    ).split(" ")[0]

    def _has_any(*phrases: str) -> bool:
        return any(p in t for p in phrases)

    concepts: dict[str, List[str]] = {
        "account": ["account", "acct", "a/c", "khata", "hisab", "cuenta", "compte", "konto", "கணக்கு", "kanakku"],
        "status": ["status", "active", "inactive", "dormant", "closed", "stithi", "estado", "statut", "நிலை", "nilamai"],
        "balance": ["balance", "saldo", "solde", "amount", "montant", "paisa", "பாலன்ஸ்", "iruppu", "balance amount"],
        "overdraft": ["overdraft", "over draft", "descubierto", "decouvert"],
        "outstanding": ["outstanding", "due", "arrears", "pending", "pendiente", "retard"],
        "account_number": ["account number", "acct number", "numero de cuenta", "numero compte", "iban"],
        "sort_code": ["sort code", "bank code", "codigo banco", "code banque"],
        "account_type": ["account type", "which account", "what account", "tipo de cuenta", "type de compte"],
        "email": ["email", "mail id", "correo", "courriel"],
        "language": ["language", "idioma", "langue", "bhasha", "மொழி", "mozhi"],
        "preference": ["preference", "preferred", "prefiero", "pasand"],
        "contact": ["contact", "contacto", "contacter", "sampark"],
        "products": ["products", "product", "services", "producto", "produits", "hold"],
        "kyc": ["kyc", "verification", "verified", "identification", "verificacion", "identite"],
        "address": ["address", "postcode", "city", "direccion", "adresse", "ville", "முகவரி", "mugavari"],
        "risk": ["risk", "churn", "riesgo", "risque"],
        "loan": ["loan", "emi", "installment", "credit", "pret", "prestamo"],
        "loan_outstanding": ["loan outstanding", "outstanding loan", "remaining loan", "solde pret", "restante prestamo"],
        "next_emi": ["next emi", "emi date", "next payment date", "proximo pago", "prochaine echeance"],
        "missed_payment": ["missed payment", "missed emi", "late payment", "pago perdido", "paiement manque"],
        "card": ["card", "debit card", "credit card", "tarjeta", "carte"],
        "card_status": ["card status", "card active", "card blocked", "estado tarjeta", "statut carte"],
        "last_txn": ["last transaction", "recent transaction", "last purchase", "ultima transaccion", "derniere transaction"],
        "card_limit": ["credit limit", "card limit", "limite", "plafond"],
        "plan": ["plan", "package", "tariff", "plan name", "திட்டம்", "thittam", "plan enna"],
        "monthly_fee": ["monthly fee", "monthly charge", "plan cost", "bill amount", "கட்டணம்", "kattanam", "monthly amount"],
        "last_bill": ["last bill", "recent bill", "previous bill", "கடைசி பில்", "kadaisi bill"],
        "payment_method": ["payment method", "autopay", "auto pay", "direct debit", "invoice", "கட்டணம் எப்படி", "payment eppadi"],
        "data_usage": ["data usage", "data used", "usage", "internet usage", "டேட்டா", "data evlo", "data usage enna"],
        "contract_end": ["contract end", "contract expiry", "renewal date", "ஒப்பந்தம் முடியும்", "expiry date"],
        "repeat_issue": ["called before", "repeat issue", "same issue", "again issue", "மீண்டும்", "marupadi"],
        "network": ["network", "signal", "outage", "coverage", "internet issue", "நெட்வொர்க்", "signal problem"],
    }

    def _has_concept(*keys: str) -> bool:
        for key in keys:
            for token in concepts.get(key, []):
                if token in t:
                    return True
        return False

    def _fmt_currency(value: Any) -> Optional[str]:
        if isinstance(value, (int, float)):
            if value < 0:
                return f"minus GBP {abs(value):.2f}"
            return f"GBP {value:.2f}"
        return None

    def _mask_account_number(value: Any) -> Optional[str]:
        if value is None:
            return None
        s = str(value).strip()
        if len(s) < 4:
            return None
        return f"ending {s[-4:]}"

    def _mask_sort_code(value: Any) -> Optional[str]:
        if value is None:
            return None
        digits = "".join(ch for ch in str(value) if ch.isdigit())
        if len(digits) != 6:
            return None
        return f"{digits[:2]}-XX-XX"

    asks_status = _has_any("account status", "status of my account") or (
        _has_concept("account") and _has_concept("status")
    )
    asks_balance = _has_any("account balance", "how much in my account") or (
        _has_concept("balance") or (_has_concept("account") and _has_any("how much", "money", "amount"))
    )
    asks_overdraft = _has_concept("overdraft")
    asks_outstanding = _has_concept("outstanding")
    asks_account_number = _has_concept("account_number")
    asks_sort_code = _has_concept("sort_code")
    asks_account_type = _has_concept("account_type")
    asks_email = _has_concept("email")
    asks_language = _has_concept("language") and _has_concept("preference")
    asks_contact = _has_concept("contact") and _has_concept("preference")
    asks_products = _has_concept("products")
    asks_kyc = _has_concept("kyc")
    asks_address = _has_concept("address")
    asks_risk = _has_concept("risk")
    asks_plan = _has_concept("plan")
    asks_monthly_fee = _has_concept("monthly_fee")
    asks_last_bill = _has_concept("last_bill")
    asks_payment_method = _has_concept("payment_method")
    asks_data_usage = _has_concept("data_usage")
    asks_contract_end = _has_concept("contract_end")
    asks_repeat_issue = _has_concept("repeat_issue")
    asks_network = _has_concept("network")

    loan = customer_profile.get("loan") if isinstance(customer_profile.get("loan"), dict) else {}
    card = customer_profile.get("card") if isinstance(customer_profile.get("card"), dict) else {}

    asks_loan = _has_concept("loan")
    asks_loan_outstanding = _has_concept("loan_outstanding")
    asks_next_emi = _has_concept("next_emi")
    asks_missed_payments = _has_concept("missed_payment")
    asks_card = _has_concept("card")
    asks_card_status = _has_concept("card_status")
    asks_last_txn = _has_concept("last_txn")
    asks_card_limit = _has_concept("card_limit")

    response_parts: List[str] = []
    intent = "account_query"

    if asks_status:
        account_status = str(customer_profile.get("account_status") or "unknown").lower()
        if account_status == "active":
            response_parts.append(f"Yes {name}, your account status is active.")
        elif account_status and account_status != "unknown":
            response_parts.append(f"{name}, your current account status is {account_status}.")
        else:
            response_parts.append(f"{name}, I could not confirm account status right now.")
        intent = "account_status"

    if asks_balance:
        balance_text = _fmt_currency(customer_profile.get("balance_gbp"))
        if balance_text:
            response_parts.append(f"Your current balance is {balance_text}.")
        else:
            outstanding_text = _fmt_currency(customer_profile.get("outstanding_balance_gbp"))
            if outstanding_text:
                response_parts.append(f"I can see an outstanding balance of {outstanding_text}.")
            else:
                response_parts.append("I cannot fetch the exact balance right now.")
        intent = "account_balance"

    if asks_overdraft:
        overdraft_text = _fmt_currency(customer_profile.get("overdraft_limit_gbp"))
        if overdraft_text:
            response_parts.append(f"Your overdraft limit is {overdraft_text}.")
        else:
            response_parts.append("I do not see an overdraft limit configured on this account.")
        intent = "overdraft_info"

    if asks_outstanding:
        outstanding_text = _fmt_currency(customer_profile.get("outstanding_balance_gbp"))
        if outstanding_text:
            response_parts.append(f"Your outstanding amount is {outstanding_text}.")
        else:
            response_parts.append("I do not see any outstanding amount in the current record.")
        intent = "outstanding_balance"

    if asks_account_number:
        masked = _mask_account_number(customer_profile.get("account_number"))
        if masked:
            response_parts.append(f"For security, your account number is {masked}.")
        else:
            response_parts.append("I can provide account number verification through a secure channel only.")
        intent = "account_identifier"

    if asks_sort_code:
        masked_sc = _mask_sort_code(customer_profile.get("sort_code"))
        if masked_sc:
            response_parts.append(f"Your sort code is {masked_sc}.")
        else:
            response_parts.append("I cannot confirm sort code right now.")
        intent = "account_identifier"

    if asks_account_type:
        account_type = customer_profile.get("account_type")
        if account_type:
            response_parts.append(f"Your account type is {str(account_type).replace('_', ' ')}.")
        else:
            response_parts.append("I cannot see account type in the current record.")
        intent = "account_type"

    if asks_email:
        email = customer_profile.get("email")
        if email:
            response_parts.append(f"Your registered email is {email}.")
        else:
            response_parts.append("I cannot see a registered email right now.")
        intent = "profile_email"

    if asks_language:
        pref_lang = customer_profile.get("language_preference")
        if pref_lang:
            response_parts.append(f"Your preferred language is {pref_lang}.")
        else:
            response_parts.append("No preferred language is set in your profile.")
        intent = "language_preference"

    if asks_contact:
        pref_contact = customer_profile.get("preferred_contact")
        if pref_contact:
            response_parts.append(f"Your preferred contact method is {pref_contact}.")
        else:
            response_parts.append("No preferred contact method is set in your profile.")
        intent = "contact_preference"

    if asks_products:
        products = customer_profile.get("products_held")
        if isinstance(products, list) and products:
            cleaned = [str(p).replace("_", " ") for p in products[:5]]
            response_parts.append(f"You currently hold: {', '.join(cleaned)}.")
        else:
            response_parts.append("I cannot find product details right now.")
        intent = "products_held"

    if asks_plan:
        plan_name = customer_profile.get("plan_name") or customer_profile.get("plan")
        if plan_name:
            response_parts.append(f"Your current plan is {plan_name}.")
        else:
            response_parts.append("I cannot find your current plan right now.")
        intent = "plan_info"

    if asks_monthly_fee:
        fee_text = _fmt_currency(customer_profile.get("monthly_fee_gbp"))
        if fee_text:
            response_parts.append(f"Your monthly plan fee is {fee_text}.")
        else:
            response_parts.append("I cannot confirm monthly fee right now.")
        intent = "billing_info"

    if asks_last_bill:
        last_bill_text = _fmt_currency(customer_profile.get("last_bill_gbp"))
        if last_bill_text:
            response_parts.append(f"Your last bill was {last_bill_text}.")
        else:
            response_parts.append("I cannot fetch your last bill amount right now.")
        intent = "billing_info"

    if asks_payment_method:
        method = customer_profile.get("payment_method")
        autopay = customer_profile.get("autopay_enabled")
        if method:
            if isinstance(autopay, bool):
                ap = "enabled" if autopay else "disabled"
                response_parts.append(f"Your payment method is {method}, and autopay is {ap}.")
            else:
                response_parts.append(f"Your payment method is {method}.")
        else:
            response_parts.append("I cannot see payment method details right now.")
        intent = "payment_method"

    if asks_data_usage:
        usage = customer_profile.get("data_usage_percent")
        if isinstance(usage, (int, float)):
            response_parts.append(f"Your data usage is currently {usage}% of your plan allowance.")
        else:
            response_parts.append("I cannot fetch current data usage right now.")
        intent = "data_usage"

    if asks_contract_end:
        contract_end = customer_profile.get("contract_end")
        if contract_end:
            response_parts.append(f"Your contract end date is {contract_end}.")
        else:
            response_parts.append("I cannot confirm contract end date right now.")
        intent = "contract_info"

    if asks_repeat_issue:
        repeat_issue = customer_profile.get("repeat_issue")
        call_count = customer_profile.get("call_history_count")
        if isinstance(repeat_issue, bool):
            if repeat_issue:
                count_text = f" with {call_count} previous calls" if isinstance(call_count, int) else ""
                response_parts.append(f"Yes, this appears as a repeat issue{count_text}.")
            else:
                response_parts.append("This issue is not marked as a repeat issue in your profile.")
        else:
            response_parts.append("I cannot determine repeat issue status right now.")
        intent = "repeat_issue"

    if asks_network:
        last_intent = str(customer_profile.get("last_call_intent") or "")
        if "network" in last_intent or "outage" in last_intent:
            response_parts.append("I can see your recent issue is related to network service.")
        else:
            response_parts.append("I can raise a technical network check for this issue.")
        intent = "network_support"

    if asks_kyc:
        kyc_status = customer_profile.get("kyc_status")
        kyc_expiry = customer_profile.get("kyc_expiry_date")
        if kyc_status:
            if kyc_expiry:
                response_parts.append(f"Your KYC status is {kyc_status}, valid until {kyc_expiry}.")
            else:
                response_parts.append(f"Your KYC status is {kyc_status}.")
        else:
            response_parts.append("I cannot confirm KYC status right now.")
        intent = "kyc_status"

    if asks_address:
        address = customer_profile.get("address")
        if isinstance(address, dict):
            city = address.get("city")
            postcode = address.get("postcode")
            line1 = address.get("line1")
            parts = [p for p in [line1, city, postcode] if p]
            if parts:
                response_parts.append(f"Your registered address is {', '.join(parts)}.")
            else:
                response_parts.append("I can see an address record but details are incomplete.")
        else:
            response_parts.append("I cannot fetch address details right now.")
        intent = "address_info"

    if asks_risk:
        risk_rating = customer_profile.get("risk_rating")
        churn_risk = customer_profile.get("churn_risk_score")
        if risk_rating:
            response_parts.append(f"Your current risk rating is {risk_rating}.")
        if isinstance(churn_risk, (int, float)):
            response_parts.append(f"Your churn risk score is {churn_risk:.2f}.")
        if not risk_rating and not isinstance(churn_risk, (int, float)):
            response_parts.append("I cannot see risk metrics in the current record.")
        intent = "risk_profile"

    if asks_loan or asks_loan_outstanding or asks_next_emi or asks_missed_payments:
        if loan:
            if asks_loan_outstanding or asks_loan:
                outstanding = _fmt_currency(loan.get("outstanding_gbp"))
                if outstanding:
                    response_parts.append(f"Your loan outstanding is {outstanding}.")
            if asks_next_emi or asks_loan:
                next_emi = loan.get("next_emi_date")
                monthly_emi = _fmt_currency(loan.get("monthly_emi_gbp"))
                if next_emi and monthly_emi:
                    response_parts.append(f"Your next EMI is {monthly_emi} on {next_emi}.")
                elif next_emi:
                    response_parts.append(f"Your next EMI date is {next_emi}.")
            if asks_missed_payments or asks_loan:
                missed = loan.get("missed_payments_count")
                if isinstance(missed, int):
                    response_parts.append(f"Missed payments count is {missed}.")
            loan_status = loan.get("loan_status")
            if asks_loan and loan_status:
                response_parts.append(f"Loan status is {str(loan_status).replace('_', ' ')}.")
        else:
            response_parts.append("I cannot find an active loan record for your profile.")
        intent = "loan_info"

    if asks_card or asks_card_status or asks_last_txn or asks_card_limit:
        if card:
            if asks_card_status or asks_card:
                card_status = card.get("card_status")
                if card_status:
                    response_parts.append(f"Your card status is {card_status}.")
            if asks_last_txn or asks_card:
                last_txn_date = card.get("last_transaction_date")
                last_txn_amt = _fmt_currency(card.get("last_transaction_gbp"))
                merchant = card.get("last_transaction_merchant")
                if last_txn_date and last_txn_amt:
                    merchant_part = f" at {merchant}" if merchant else ""
                    response_parts.append(
                        f"Last transaction was {last_txn_amt} on {last_txn_date}{merchant_part}."
                    )
            if asks_card_limit:
                card_limit = _fmt_currency(card.get("credit_limit_gbp"))
                if card_limit:
                    response_parts.append(f"Your card credit limit is {card_limit}.")
                else:
                    response_parts.append("No credit limit is set for this card.")
        else:
            response_parts.append("I cannot find card details for your profile.")
        intent = "card_info"

    if not response_parts:
        return None

    # Keep response short and direct for voice interactions.
    compact = " ".join(response_parts[:3])
    return {
        "response": f"{name}, {compact}",
        "intent": intent,
    }


def _fallback_live_response(customer_name: str, user_text: str) -> str:
    """Guarantee a spoken response if model output is empty."""
    lowered = (user_text or "").lower()
    first_name = (customer_name or "Customer").split(" ")[0]

    if any(k in lowered for k in ["network", "signal", "internet", "coverage", "outage"]):
        return (
            f"I understand, {first_name}. I can see this is a network issue. "
            "I will run targeted checks and guide you step by step right now."
        )
    if any(k in lowered for k in ["bill", "charge", "charged", "payment", "refund"]):
        return (
            f"Thanks for explaining, {first_name}. I will help with the billing concern now. "
            "Please share the charge amount and date so I can verify it immediately."
        )

    return (
        f"Thanks for the details, {first_name}. I am with you on this. "
        "Let me work through the issue and get this resolved quickly."
    )


def _detect_human_handoff_request(user_text: str) -> List[str]:
    """Detect direct customer requests to speak with a person/manager."""
    text = (user_text or "").lower()
    phrases = [
        "connect me",
        "connect to",
        "talk to a person",
        "talk to a human",
        "speak to a person",
        "speak to a human",
        "speak to manager",
        "talk to manager",
        "transfer me",
        "agent please",
        "representative",
        "supervisor",
    ]
    return [p for p in phrases if p in text]


def _detect_out_of_scope_handoff_request(user_text: str) -> List[str]:
    """Detect domain/department queries that should be routed to a human specialist."""
    text = (user_text or "").lower()
    phrases = [
        "manager team",
        "branch manager",
        "relationship manager",
        "senior manager",
        "approval team",
        "underwriting team",
        "legal team",
        "compliance team",
        "risk team",
        "fraud team",
        "back office",
        "head office",
        "complaint department",
        "collections department",
        "loan restructuring",
        "manual approval",
        "department number",
        "specialist team",
    ]
    return [p for p in phrases if p in text]


def _is_question_like(text: str) -> bool:
    t = (text or "").lower().strip()
    if not t:
        return False
    if "?" in t:
        return True
    return any(
        w in t
        for w in [
            "what",
            "why",
            "how",
            "when",
            "where",
            "which",
            "who",
            "can you",
            "could you",
            "tell me",
            "explain",
            "check",
            "enna",
            "epdi",
            "eppadi",
            "sollu",
            "என்ன",
            "எப்படி",
            "சொல்ல",
        ]
    )


def _should_escalate_unanswerable(
    user_text: str,
    ai_text: str,
    intent: str,
    direct_db_answered: bool,
    ai_confidence: int,
) -> bool:
    """Escalate if request appears out-of-scope or unresolved by agent/DB."""
    if direct_db_answered:
        return False

    normalized_intent = (intent or "").lower()
    if normalized_intent in ["greeting", "small_talk"]:
        return False

    question_like = _is_question_like(user_text)
    if not question_like:
        return False

    answer = (ai_text or "").lower()
    unresolved_markers = [
        "cannot fetch",
        "cannot confirm",
        "cannot see",
        "cannot find",
        "could not confirm",
        "i am not sure",
        "i don't have",
        "i do not have",
        "temporarily unavailable",
        "specialist",
        "manual review",
    ]
    looks_unresolved = any(m in answer for m in unresolved_markers)

    very_low_confidence = ai_confidence < 55
    generic_non_answer = len(answer.strip()) < 20

    return looks_unresolved or very_low_confidence or generic_non_answer


def _build_takeover_suggestions(ai_text: str, sentiment: str, urgency: str) -> List[dict[str, str]]:
    """Provide compact AI-assist suggestions for human takeover panel."""
    suggestions: List[dict[str, str]] = []
    base_text = (ai_text or "").strip()

    if base_text:
        suggestions.append(
            {
                "suggestion": f"You can say: {base_text}",
                "tone": "manager-script",
            }
        )

    if sentiment in ["angry", "frustrated"] or urgency == "high":
        suggestions.append(
            {
                "suggestion": "You can say: I understand your frustration. I am taking ownership now and will stay with you until this is resolved.",
                "tone": "de-escalation-script",
            }
        )

    suggestions.append(
        {
            "suggestion": "You can say: I have your account details and context already. I will do a quick root-cause check and confirm the exact next step in one minute.",
            "tone": "ownership-script",
        }
    )

    # Keep top 3 unique suggestions.
    seen = set()
    unique: List[dict[str, str]] = []
    for item in suggestions:
        key = item["suggestion"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
        if len(unique) == 3:
            break

    return unique

app = FastAPI(title="Telecom AI Call System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CustomerCreate(BaseModel):
    name: str
    phone: str
    plan: str = "Basic"


class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: str
    plan: str

    class Config:
        from_attributes = True


class CallStart(BaseModel):
    customer_id: int


class CallResponse(BaseModel):
    id: int
    customer_id: int
    start_time: datetime
    status: str

    class Config:
        from_attributes = True


class MessageRequest(BaseModel):
    call_id: int
    message: str


class MessageResponse(BaseModel):
    ai_response: str
    intent: str
    sentiment: str
    urgency: str
    escalation_alert: bool = False
    trigger_phrases: List[str] = []
    suggestions: Optional[List[dict[str, str]]] = None


class ConversationItem(BaseModel):
    speaker: str
    message: str
    timestamp: datetime
    intent: Optional[str] = None
    sentiment: Optional[str] = None

    class Config:
        from_attributes = True


class SummaryResponse(BaseModel):
    summary: str
    issue: str
    sentiment: str
    resolved: bool
    action: str
    compliance: str
    decision: str

    class Config:
        from_attributes = True


class MemoryItem(BaseModel):
    issue: str
    status: str
    sentiment: Optional[str]
    resolution: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class CallHistoryItem(BaseModel):
    id: int
    start_time: datetime
    end_time: Optional[datetime]
    status: str
    summary: Optional[str] = None
    issue: Optional[str] = None
    resolved: Optional[bool] = None


class ResetResponse(BaseModel):
    message: str
    customers: int


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer: Optional[dict[str, Any]] = None
    language_history: Optional[List[str]] = None
    session_id: Optional[str] = None


class SummaryRequest(BaseModel):
    transcript: List[Message]
    session_id: Optional[str] = None
    customer_phone: Optional[str] = None


class OutboundRequest(BaseModel):
    customer_id: str
    call_purpose: str = "renewal"


class OutboundRespondRequest(BaseModel):
    session_id: str
    response: str = ""


class OutboundEndRequest(BaseModel):
    session_id: str
    outcome: str = "partial"
    notes: str = ""


class SimulationStartRequest(BaseModel):
    script_id: str


class CallOutcomeRequest(BaseModel):
    session_id: str
    customer_id: str
    resolution: str


class ResolveEscalationRequest(BaseModel):
    session_id: str


@app.on_event("startup")
async def startup() -> None:
    init_db()
    await warmup_model()
    
    # Load RAG system at startup
    from rag_service import warmup_rag
    rag_ready = warmup_rag(client_id="telecorp")
    if rag_ready:
        print("RAG system ready — semantic search enabled.")
    else:
        print("RAG not ready — falling back to keyword matching.")

    asyncio.create_task(cleanup_task())


async def cleanup_task() -> None:
    """Periodically clean up expired in-memory call contexts."""
    while True:
        await asyncio.sleep(3600)
        cleanup_old_memories(max_age_hours=24)
        cleanup_temp_cache(max_age_minutes=180)


async def warmup_model() -> None:
    """Send a tiny request to preload the model into memory."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            await client.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.2:3b",
                    "prompt": "Hi",
                    "stream": False,
                    "options": {"num_predict": 5},
                },
            )
        print("Model warmed up and ready.")
    except Exception as e:
        print(f"Warmup failed (Ollama may not be running): {e}")


@app.get("/health")
async def health_check():
    ollama_status = await check_ollama_status()
    client_id = get_client_id()
    client_name = "TeleCorp" if client_id.lower() == "telecorp" else client_id.title()
    return {
        "status": "healthy",
        "ollama": "connected" if ollama_status else "disconnected",
        "client_id": client_id,
        "client_name": client_name,
    }


@app.get("/customers", response_model=List[CustomerResponse])
def get_customers(db: Session = Depends(get_db)):
    return db.query(Customer).all()


@app.get("/customers/{customer_id}", response_model=CustomerResponse)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@app.post("/customers", response_model=CustomerResponse)
def create_customer(customer: CustomerCreate, db: Session = Depends(get_db)):
    db_customer = Customer(**customer.model_dump())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer


@app.get("/customers/{customer_id}/memory", response_model=List[MemoryItem])
def get_customer_memory(customer_id: int, db: Session = Depends(get_db)):
    memories = (
        db.query(Memory)
        .filter(Memory.customer_id == customer_id)
        .order_by(Memory.created_at.desc())
        .limit(10)
        .all()
    )
    return memories


@app.get("/customers/{customer_id}/calls", response_model=List[CallHistoryItem])
def get_customer_calls(customer_id: int, limit: int = 10, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    calls = (
        db.query(Call)
        .filter(Call.customer_id == customer_id)
        .order_by(Call.start_time.desc())
        .limit(limit)
        .all()
    )

    summary_map: dict[int, Summary] = {}
    if calls:
        call_ids: List[int] = [cast(int, c.id) for c in calls]
        summaries = db.query(Summary).filter(Summary.call_id.in_(call_ids)).all()
        summary_map = {cast(int, s.call_id): s for s in summaries}

    result: List[CallHistoryItem] = []
    for call in calls:
        call_id = cast(int, call.id)
        summary_obj = summary_map.get(call_id)
        result.append(
            CallHistoryItem(
                id=call_id,
                start_time=cast(datetime, call.start_time),
                end_time=cast(Optional[datetime], call.end_time),
                status=cast(str, call.status),
                summary=cast(Optional[str], summary_obj.summary) if summary_obj else None,
                issue=cast(Optional[str], summary_obj.issue) if summary_obj else None,
                resolved=cast(Optional[bool], summary_obj.resolved) if summary_obj else None,
            )
        )
    return result


@app.post("/calls/start", response_model=CallResponse)
def start_call(call_data: CallStart, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == call_data.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    call = Call(customer_id=call_data.customer_id, status="active")
    db.add(call)
    db.commit()
    db.refresh(call)

    # Initialize in-memory rolling context for this call with known customer profile.
    customer_profile = _enrich_customer_profile({
        "id": cast(int, customer.id),
        "name": cast(str, customer.name),
        "plan": cast(str, customer.plan),
        "phone": cast(str, customer.phone),
    })

    # Snapshot recent memory once into temp store for fast per-turn access.
    memories = (
        db.query(Memory)
        .filter(Memory.customer_id == call.customer_id)
        .order_by(Memory.created_at.desc())
        .limit(5)
        .all()
    )
    phone_cache = get_phone_cache(customer_profile.get("phone"))
    cached_memory_lines = []
    if phone_cache:
        cached_memory_lines = list(phone_cache.get("memory_lines") or [])
    memory_lines = cached_memory_lines or _memory_lines(memories)

    hydrate_call_cache(cast(int, call.id), customer_profile=customer_profile, memory_lines=memory_lines)
    CALL_CONTEXT[cast(int, call.id)] = _new_context(customer_profile=customer_profile)
    return call


@app.post("/calls/{call_id}/message", response_model=MessageResponse)
async def send_message(call_id: int, request: MessageRequest, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if cast(str, call.status) != "active":
        raise HTTPException(status_code=400, detail="Call is not active")

    customer_profile = _enrich_customer_profile({
        "id": cast(int, call.customer.id),
        "name": cast(str, call.customer.name),
        "plan": cast(str, call.customer.plan),
        "phone": cast(str, call.customer.phone),
    })
    context = CALL_CONTEXT.setdefault(call_id, _new_context(customer_profile=customer_profile))
    context["customer_profile"] = customer_profile
    context["state"]["known_customer"] = True
    context["state"]["verification_complete"] = True

    # Fast path: read customer context from temp cache.
    call_cache = get_call_cache(call_id)
    if not call_cache:
        memories = (
            db.query(Memory)
            .filter(Memory.customer_id == call.customer_id)
            .order_by(Memory.created_at.desc())
            .limit(5)
            .all()
        )
        call_cache = hydrate_call_cache(call_id, customer_profile=customer_profile, memory_lines=_memory_lines(memories))

    customer_conv = Conversation(
        call_id=call_id,
        speaker="customer",
        message=request.message,
        intent=None,
        sentiment=None,
    )
    db.add(customer_conv)
    db.flush()
    temp_append_turn(call_id, role="customer", content=request.message)

    _append_history(context, "Customer", request.message)

    runtime_customer = cast(dict[str, Any], context.get("customer_profile") or customer_profile)
    ai_result: dict[str, Any] = {}

    direct_result = _direct_db_response(request.message, runtime_customer)
    if direct_result:
        ai_text = str(direct_result.get("response") or "").strip()
        intent = str(direct_result.get("intent") or detect_intent(request.message))
    else:
        ai_result = await get_contextual_ai_response(
            current_input=request.message,
            conversation_history=list(context["history"]),
            state=context["state"],
            customer_info=runtime_customer,
            memory=list(call_cache.get("memory_lines") or []),
        )
        ai_text = str(ai_result.get("response", "") or "").strip()
        if not ai_text:
            ai_text = _fallback_live_response(cast(str, call.customer.name), request.message)
        intent = ai_result.get("intent") or detect_intent(request.message)

    # Keep deterministic safety rules in backend.
    sentiment = ai_result.get("sentiment") or detect_sentiment(request.message)
    urgency = (ai_result.get("urgency") if not direct_result else None) or detect_urgency(request.message, sentiment)

    if "frustrated" in (request.message or "").lower():
        sentiment = "frustrated"
    if any(w in (request.message or "").lower() for w in ["angry", "worst", "urgent"]):
        urgency = "high"

    handoff_phrases = _detect_human_handoff_request(request.message)
    handoff_requested = len(handoff_phrases) > 0
    out_of_scope_phrases = _detect_out_of_scope_handoff_request(request.message)
    out_of_scope_requested = len(out_of_scope_phrases) > 0
    ai_confidence = int(ai_result.get("confidence") or 60)
    unresolved_requested = _should_escalate_unanswerable(
        user_text=request.message,
        ai_text=ai_text,
        intent=str(intent),
        direct_db_answered=bool(direct_result),
        ai_confidence=ai_confidence,
    )

    unresolved_phrases = ["unanswerable_or_out_of_db_query"] if unresolved_requested else []

    if handoff_requested or out_of_scope_requested or unresolved_requested:
        urgency = "high"
        intent = "human_escalation"
        customer_name = str(runtime_customer.get("name") or runtime_customer.get("full_name") or "Customer").split(" ")[0]
        ai_text = (
            f"{customer_name}, this request needs a human specialist team. "
            "I am escalating your call now and connecting you to the right manager team."
        )

    _update_state_from_user(context, request.message, intent)
    _update_state_from_ai(context, ai_text)
    _append_history(context, "AI", ai_text)

    suggestions = _build_takeover_suggestions(ai_text, str(sentiment), str(urgency))
    trigger_phrases = handoff_phrases + [p for p in out_of_scope_phrases if p not in handoff_phrases]
    trigger_phrases += [p for p in unresolved_phrases if p not in trigger_phrases]
    escalation_alert = handoff_requested or out_of_scope_requested or unresolved_requested or (str(sentiment).lower() == "angry" and str(urgency).lower() == "high")

    ai_conv = Conversation(call_id=call_id, speaker="ai", message=ai_text)
    db.add(ai_conv)
    temp_append_turn(call_id, role="ai", content=ai_text, intent=str(intent), sentiment=str(sentiment))

    # Persist detected metadata for transcript intelligence.
    setattr(customer_conv, "intent", cast(Any, intent))
    setattr(customer_conv, "sentiment", cast(Any, sentiment))
    db.commit()

    return MessageResponse(
        ai_response=ai_text,
        intent=intent,
        sentiment=sentiment,
        urgency=urgency,
        escalation_alert=escalation_alert,
        trigger_phrases=trigger_phrases,
        suggestions=suggestions,
    )


@app.post("/calls/{call_id}/end", response_model=SummaryResponse)
async def end_call(call_id: int, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    conversations = (
        db.query(Conversation)
        .filter(Conversation.call_id == call_id)
        .order_by(Conversation.timestamp)
        .all()
    )
    transcript = [
        {
            "role": "user" if cast(str, c.speaker) == "customer" else "assistant",
            "content": cast(str, c.message),
        }
        for c in conversations
    ]

    memories = (
        db.query(Memory)
        .filter(Memory.customer_id == call.customer_id)
        .order_by(Memory.created_at.desc())
        .limit(5)
        .all()
    )
    history = "\n".join([f"- {m.issue} ({m.status})" for m in memories]) if memories else ""

    summary_data = await generate_call_summary(transcript, history)

    resolution = summary_data.get("resolution", "unresolved")
    resolved = resolution == "resolved"
    action = summary_data.get("recommended_action", "Manual review required")
    decision = "resolve" if resolved else "follow_up"

    summary = Summary(
        call_id=call_id,
        summary=summary_data.get("summary", ""),
        issue=summary_data.get("issue", "other"),
        sentiment=summary_data.get("sentiment", "neutral"),
        resolved=resolved,
        action=action,
        compliance="ok",
        decision=decision,
    )
    db.add(summary)

    memory = Memory(
        customer_id=call.customer_id,
        issue=summary_data.get("issue", "General inquiry"),
        status="resolved" if resolved else "unresolved",
        sentiment=summary_data.get("sentiment"),
        resolution=action,
    )
    db.add(memory)

    issue_line = f"- {summary_data.get('issue', 'General inquiry')} ({'resolved' if resolved else 'unresolved'})"
    refresh_phone_cache_from_call(call_id, new_issue_line=issue_line)

    setattr(call, "status", cast(Any, "completed"))
    setattr(call, "end_time", cast(Any, datetime.utcnow()))
    db.commit()

    # Release in-memory context for ended calls.
    CALL_CONTEXT.pop(call_id, None)
    end_call_cache(call_id)

    return SummaryResponse(
        summary=summary_data.get("summary", ""),
        issue=summary_data.get("issue", "other"),
        sentiment=summary_data.get("sentiment", "neutral"),
        resolved=resolved,
        action=action,
        compliance="ok",
        decision=decision,
    )


@app.get("/calls/{call_id}/transcript", response_model=List[ConversationItem])
def get_transcript(call_id: int, db: Session = Depends(get_db)):
    conversations = (
        db.query(Conversation)
        .filter(Conversation.call_id == call_id)
        .order_by(Conversation.timestamp)
        .all()
    )
    return conversations


@app.get("/calls/{call_id}/summary", response_model=SummaryResponse)
def get_summary(call_id: int, db: Session = Depends(get_db)):
    summary = db.query(Summary).filter(Summary.call_id == call_id).first()
    if not summary:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Enhanced chat endpoint with language detection, memory, and escalation signals."""
    try:
        session_id = request.session_id or str(uuid.uuid4())
        context = CHAT_SESSION_CONTEXT.setdefault(session_id, _new_context())
        context.setdefault("sentiments", [])

        customer_obj = request.customer or {}
        customer_id_any = customer_obj.get("id") or request.customer_phone
        customer_id = str(customer_id_any) if customer_id_any is not None else None
        memory = get_or_create_memory(session_id, customer_id)

        messages = [m.model_dump() for m in request.messages]

        latest_customer_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_customer_msg = msg.get("content", "")
                break

        if not latest_customer_msg:
            return {
                "response": "Hello, how can I help you today?",
                "ai_response": "Hello, how can I help you today?",
                "intent": "general",
                "sentiment": "neutral",
                "sentiment_score": 0.0,
                "urgency": "low",
                "trajectory": "stable",
                "trigger_phrase": None,
                "churn_risk": False,
                "escalation_needed": False,
                "suggestions": [],
                "language": "en",
                "language_detected": "en",
                "de_escalation": None,
                "rag_sources": [],
                "session_id": session_id,
            }

        _append_history(context, "Customer", latest_customer_msg)

        detected_language = detect_language(latest_customer_msg)
        response_language = get_response_language(detected_language, request.language_history or memory.language_history)
        sentiment_result = detect_sentiment_ml(latest_customer_msg, detected_language)
        context["sentiments"].append(sentiment_result)
        trajectory = get_sentiment_arc(context["sentiments"])
        if trajectory not in ["worsening", "stable", "improving"]:
            trajectory = "stable"
        sentiment_result.trajectory = cast(Any, trajectory)

        memory.add_turn(
            role="user",
            content=latest_customer_msg,
            sentiment=sentiment_result.score,
            intent=detect_intent(latest_customer_msg),
            language=detected_language,
        )

        ai_result = await get_ai_response(
            messages=messages,
            customer=customer_obj or {
                "name": request.customer_name,
                "phone": request.customer_phone,
            },
        )

        response_text = str(ai_result.get("response", "")).strip()
        intent = str(ai_result.get("intent") or detect_intent(latest_customer_msg))

        _update_state_from_user(context, latest_customer_msg, intent)
        _update_state_from_ai(context, response_text)
        _append_history(context, "AI", response_text)

        memory.add_turn(
            role="assistant",
            content=response_text,
            intent=intent,
            language=response_language,
            suggestions=ai_result.get("suggestions", []),
        )

        language_mode = "tamil" if detected_language == "ta" else detected_language
        abusive_detected, abusive_matches = detect_abusive_language(latest_customer_msg, language_mode=language_mode)
        angry_turns = sum(1 for score in memory.sentiment_history if score < -0.7)
        should_auto_escalate = (
            (sentiment_result.label == "angry" and angry_turns >= 2)
            or abusive_detected
            or sentiment_result.churn_risk
        )

        if should_auto_escalate:
            memory.escalation_triggered = True

        customer_display = (
            str(customer_obj.get("name") or customer_obj.get("full_name") or request.customer_name or "Customer")
        )
        de_escalation = None
        if sentiment_result.label in ["angry", "frustrated", "mildly_frustrated"] or should_auto_escalate:
            de_escalation = get_de_escalation_suggestion(sentiment_result, customer_display, response_language)

        return {
            "response": response_text,
            "ai_response": response_text,
            "intent": intent,
            "sentiment": sentiment_result.label,
            "sentiment_score": sentiment_result.score,
            "urgency": urgency_level(sentiment_result),
            "trajectory": sentiment_result.trajectory,
            "trigger_phrase": sentiment_result.trigger_phrase,
            "trigger_phrases": [sentiment_result.trigger_phrase] if sentiment_result.trigger_phrase else [],
            "churn_risk": sentiment_result.churn_risk,
            "escalation_needed": sentiment_result.escalation_needed or should_auto_escalate,
            "escalation_alert": should_auto_escalate,
            "auto_escalated": should_auto_escalate,
            "angry_turns": angry_turns,
            "abusive_language_detected": abusive_detected,
            "abusive_matches": sorted(list(abusive_matches)),
            "suggestions": ai_result.get("suggestions", []),
            "language": response_language,
            "language_mode": response_language,
            "language_detected": detected_language,
            "language_instruction": get_system_prompt_language_instruction(response_language),
            "de_escalation": de_escalation,
            "rag_sources": ai_result.get("rag_sources", []),
            "memory_context": memory.get_context_for_prompt(),
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/summary")
async def api_summary(request: SummaryRequest):
    """Generate a post-call summary from full transcript only."""
    transcript = [m.model_dump() for m in request.transcript]
    summary_data = await generate_call_summary(transcript)

    if request.session_id:
        save_call_session(
            {
                "id": request.session_id,
                "customer_id": request.customer_phone,
                "call_type": "inbound",
                "call_mode": "assisted",
                "started_at": datetime.utcnow().isoformat(),
                "ended_at": datetime.utcnow().isoformat(),
                "transcript": transcript,
                "intent": summary_data.get("issue"),
                "resolution": summary_data.get("resolution"),
                "summary": summary_data.get("summary"),
            }
        )

    return summary_data


@app.post("/api/outbound/start")
async def start_outbound_call_endpoint(req: OutboundRequest):
    """Start outbound call session."""
    customer = get_customer_by_id(req.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    return start_outbound(
        customer_id=req.customer_id,
        customer_name=customer.get("full_name", "Customer"),
        call_type=req.call_purpose,
    )


@app.post("/api/outbound/respond")
async def respond_to_outbound_call(req: OutboundRespondRequest):
    """Process customer response in outbound call."""
    result = process_outbound_response(req.session_id, req.response)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/api/outbound/end")
async def end_outbound_call_endpoint(req: OutboundEndRequest):
    """End outbound call session."""
    result = end_outbound_call(req.session_id, req.outcome, req.notes)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/outbound/candidates")
async def get_outbound_call_candidates():
    """Get candidate customers for outbound call categories."""
    customers = get_all_customers()
    return {
        "renewal": [c for c in customers if is_renewal_due(c)],
        "upsell": [c for c in customers if float(c.get("upsell_score") or 0) > 0.7],
        "collections": [c for c in customers if float(c.get("outstanding_balance_gbp") or 0) > 0],
        "churn_win_back": [c for c in customers if float(c.get("churn_risk_score") or 0) > 0.6],
    }


@app.get("/api/scripts")
async def get_scripts():
    """Get available simulation scripts."""
    return get_available_scripts()


@app.post("/api/simulation/start")
async def start_simulation_endpoint(req: SimulationStartRequest):
    """Start a simulation session."""
    result = start_sim(req.script_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/simulation/next/{session_id}")
async def get_simulation_turn_endpoint(session_id: str):
    """Get next turn in simulation and attach analysis for customer turns."""
    turn_data = get_next_sim_turn(session_id)
    if "error" in turn_data:
        raise HTTPException(status_code=404, detail=turn_data["error"])
    if turn_data.get("completed"):
        return turn_data

    if turn_data.get("speaker") == "customer":
        analysis_request = ChatRequest(
            messages=[Message(role="user", content=str(turn_data.get("text", "")))],
            session_id=session_id,
        )
        analysis = await chat(analysis_request)
        turn_data["ai_analysis"] = analysis

        sim_script = get_sim_session(session_id)
        if sim_script:
            sim_script.advance_turn(analysis)

    return turn_data


@app.post("/api/simulation/end/{session_id}")
async def end_simulation_endpoint(session_id: str):
    """End simulation and return report."""
    result = end_simulation(session_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.post("/api/escalation/resolve/{session_id}")
async def resolve_escalation_endpoint(session_id: str):
    """Restore AI control after human takeover."""
    memory = get_or_create_memory(session_id)
    memory.escalation_triggered = False
    memory.human_takeover_active = False

    return {
        "status": "ai_restored",
        "session_id": session_id,
        "message": "AI control restored. Resuming automated assistance.",
        "success": True,
    }


@app.get("/api/escalation/status/{session_id}")
async def check_escalation_status(session_id: str):
    """Check escalation state for a session."""
    memory = get_or_create_memory(session_id)
    return {
        "session_id": session_id,
        "escalated": memory.escalation_triggered,
        "human_takeover_active": memory.human_takeover_active,
    }


@app.get("/api/customer-pattern/{customer_id}")
async def get_customer_pattern_endpoint(customer_id: str):
    """Get cross-call customer pattern."""
    pattern = get_customer_pattern(customer_id)
    if not pattern:
        return {"message": "No pattern data yet"}
    return pattern


@app.get("/api/customer-summary/{customer_id}")
async def get_customer_summary_endpoint(customer_id: str):
    """Get summarized customer profile with risk/repeat issue context."""
    return get_customer_summary(customer_id)


@app.post("/calls/outcome")
async def save_call_outcome(req: CallOutcomeRequest):
    """Persist lightweight call outcome for frontend integration compatibility."""
    save_call_session(
        {
            "id": req.session_id,
            "customer_id": req.customer_id,
            "call_type": "inbound",
            "call_mode": "assisted",
            "started_at": datetime.utcnow().isoformat(),
            "ended_at": datetime.utcnow().isoformat(),
            "resolution": req.resolution,
        }
    )
    return {"success": True, "message": "Outcome stored"}


@app.post("/calls/resolve-escalation")
async def resolve_escalation_post(req: ResolveEscalationRequest):
    """Frontend helper endpoint to clear escalation on a session."""
    memory = get_or_create_memory(req.session_id)
    memory.escalation_triggered = False
    memory.human_takeover_active = False
    return {"success": True, "message": "Escalation resolved"}


@app.get("/api/customer/{phone}")
async def api_customer(phone: str):
    customer = get_customer_by_phone(phone)
    if not customer:
        return {"found": False}
    return {"found": True, "customer": customer}


@app.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    total_calls = db.query(Call).count()
    active_calls = db.query(Call).filter(Call.status == "active").count()
    resolved_issues = db.query(Memory).filter(Memory.status == "resolved").count()
    unresolved_issues = db.query(Memory).filter(Memory.status == "unresolved").count()

    return {
        "total_calls": total_calls,
        "active_calls": active_calls,
        "resolved_issues": resolved_issues,
        "unresolved_issues": unresolved_issues,
    }


@app.delete("/admin/reset-demo-data", response_model=ResetResponse)
def reset_demo_data(db: Session = Depends(get_db)):
    db.query(Conversation).delete(synchronize_session=False)
    db.query(Summary).delete(synchronize_session=False)
    db.query(Call).delete(synchronize_session=False)
    db.query(Memory).delete(synchronize_session=False)
    db.query(Customer).delete(synchronize_session=False)
    db.commit()

    sample_customers = [
        Customer(name="James Richardson", phone="+1234567890", plan="Premium"),
        Customer(name="Jane Smith", phone="+0987654321", plan="Basic"),
        Customer(name="Bob Wilson", phone="+1122334455", plan="Business"),
    ]
    db.add_all(sample_customers)
    db.commit()

    return ResetResponse(
        message="Old records deleted and default customers re-seeded.",
        customers=len(sample_customers),
    )


def detect_intent(text: str) -> str:
    text = (text or "").lower()
    if any(w in text for w in ["bill", "charge", "invoice", "refund", "payment", "charged"]):
        return "billing_dispute"
    if any(w in text for w in ["signal", "network", "outage", "slow", "internet", "connection"]):
        return "network_outage"
    if any(w in text for w in ["upgrade", "more data", "better plan", "unlimited"]):
        return "plan_upgrade"
    if any(w in text for w in ["cancel", "leave", "switch", "bt", "vodafone", "quit"]):
        return "churn_risk"
    if any(w in text for w in ["can't pay", "payment plan", "extension", "afford"]):
        return "collections_payment"
    if any(w in text for w in ["sim", "replace", "lost", "stolen", "esim"]):
        return "sim_swap"
    if any(w in text for w in ["roam", "abroad", "spain", "france", "travel"]):
        return "roaming_query"
    if any(w in text for w in ["complaint", "manager", "ofcom", "terrible", "useless"]):
        return "complaint_formal"
    if any(w in text for w in ["number", "port", "transfer", "pac code", "keep my number"]):
        return "number_porting"
    if any(w in text for w in ["downgrade", "cheaper", "reduce", "smaller"]):
        return "plan_downgrade"
    return "account_query"


def detect_sentiment(text: str) -> str:
    text = (text or "").lower()
    angry = [
        "terrible",
        "useless",
        "furious",
        "disgusting",
        "unacceptable",
        "awful",
        "worst",
        "ridiculous",
        "incompetent",
        "pathetic",
    ]
    frustrated = [
        "frustrated",
        "annoyed",
        "unhappy",
        "disappointed",
        "again",
        "still not",
        "never fixed",
        "third time",
        "keeps happening",
    ]
    positive = ["thank", "great", "appreciate", "happy", "excellent", "perfect"]

    if any(w in text for w in angry):
        return "angry"
    if any(w in text for w in frustrated):
        return "frustrated"
    if any(w in text for w in positive):
        return "positive"
    return "neutral"


def detect_urgency(text: str, sentiment: str) -> str:
    text = (text or "").lower()
    if sentiment == "angry" or any(
        w in text for w in ["emergency", "urgent", "immediately", "right now", "cancel", "ofcom"]
    ):
        return "high"
    if sentiment == "frustrated" or any(
        w in text for w in ["been waiting", "three times", "still", "again", "week"]
    ):
        return "medium"
    return "low"


def is_renewal_due(customer: dict) -> bool:
    """Check if a contract appears due for renewal within 30 days."""
    contract_end = customer.get("contract_end")
    if not contract_end:
        return False
    try:
        contract_date = datetime.fromisoformat(str(contract_end).replace("Z", "+00:00"))
    except ValueError:
        return False
    renewal_window = datetime.utcnow() + timedelta(days=30)
    # Compare as naive UTC for simplicity across stored formats.
    contract_naive = contract_date.replace(tzinfo=None)
    return contract_naive <= renewal_window


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8030)
