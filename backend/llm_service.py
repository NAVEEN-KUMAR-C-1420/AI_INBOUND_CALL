import httpx
import json
import re
import os
import time
from typing import Any, Optional, Dict, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from config import get_kb
from database import get_customer_by_name, get_customer_by_phone, get_all_kb_context
from rag_service import build_rag_prompt, get_rag_context_for_display

# LLM Config
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
FALLBACK_MODELS = [DEFAULT_OLLAMA_MODEL, "llama3.2:latest", "llama3", "qwen3:4b", "qwen2.5:3b", "mistral"]

# Gemini Config
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# OpenRouter Config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
DEFAULT_OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")
OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "http://localhost:8000")
OPENROUTER_APP_NAME = os.getenv("OPENROUTER_APP_NAME", "Telecom AI Call System")

# Groq Config
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
DEFAULT_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Together AI Config
TOGETHER_API_KEY = os.getenv("TOGETHER_API_KEY", "")
DEFAULT_TOGETHER_MODEL = os.getenv("TOGETHER_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")


SUMMARY_INTENTS = {
    "billing_dispute",
    "network_outage",
    "plan_upgrade",
    "plan_downgrade",
    "churn_risk",
    "collections_payment",
    "technical_support",
    "number_porting",
    "sim_swap",
    "roaming_query",
    "account_query",
    "complaint_formal",
}


def _infer_issue_from_transcript(transcript: list) -> str:
    """Pick the most recent concrete intent from customer turns."""
    for msg in reversed(transcript or []):
        role = msg.get("role") or ("user" if msg.get("speaker") == "customer" else "assistant")
        if role != "user":
            continue
        content = str(msg.get("content") or msg.get("message") or "").strip()
        if not content:
            continue
        inferred = _fallback_intent(content)
        if inferred and inferred != "other":
            return inferred
    return "account_query"


def _normalize_summary_issue(issue: Any, transcript: list) -> str:
    value = str(issue or "").strip().lower()
    if value in SUMMARY_INTENTS:
        return value
    if value == "other" or not value:
        return _infer_issue_from_transcript(transcript)
    return _infer_issue_from_transcript(transcript)


def _normalize_summary_resolution(resolution: Any) -> str:
    value = str(resolution or "").strip().lower().replace(" ", "_")
    if value == "resolved":
        return "resolved"
    if value == "escalated":
        return "escalated"
    if value in {"unresolved", "callback_required", "follow_up", "pending", "in_progress"}:
        return "unresolved"
    return "unresolved"


def _is_customer_known(customer_info: Optional[dict]) -> bool:
    if not customer_info:
        return False
    return bool(customer_info.get("name") or customer_info.get("phone") or customer_info.get("id"))


def _is_reverification_request(text: str) -> bool:
    t = (text or "").lower()
    patterns = [
        "full name",
        "name, address",
        "address, age",
        "email",
        "verify your account",
        "share your",
    ]
    return any(p in t for p in patterns)


async def _resolve_ollama_model() -> str:
    """Pick the first preferred model available locally in Ollama."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            response.raise_for_status()
            tags = response.json().get("models", [])
            available = [m.get("name") for m in tags if m.get("name")]

        for preferred in FALLBACK_MODELS:
            if preferred in available:
                return preferred

        if available:
            return available[0]
    except Exception:
        pass

    return DEFAULT_OLLAMA_MODEL


def _extract_json_payload(text: str) -> Optional[dict]:
    """Extract and parse the first JSON object from model output."""
    if not text:
        return None

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Handle occasional Python-style booleans in model output.
        normalized = candidate.replace("True", "true").replace("False", "false")
        try:
            return json.loads(normalized)
        except json.JSONDecodeError:
            return None


def _fallback_agent_response(user_text: str, customer_info: Optional[dict] = None) -> str:
    """Deterministic fallback response when model is unavailable."""
    text = (user_text or "").lower()
    known_customer = _is_customer_known(customer_info)

    if any(w in text for w in ["charge", "charged", "bill", "billing", "refund", "invoice"]):
        return (
            "I understand your billing concern, and I will help sort this out right away. "
            "Please confirm the date and amount of the extra charge, and I will guide you through the correction."
        )

    if any(w in text for w in ["signal", "network", "internet", "outage", "no signal", "connection"]):
        return (
            "I am sorry you are facing a network issue. "
            "Please share your postcode and whether this affects calls, data, or both so I can run the right checks."
        )

    if any(w in text for w in ["upgrade", "downgrade", "plan", "data", "unlimited"]):
        return (
            "I can help with your plan change. "
            "Please tell me your current plan and what you want to improve, and I will suggest the best option."
        )

    if any(w in text for w in ["cancel", "leave", "switch", "port", "pac"]):
        return (
            "I understand you are considering a switch, and I want to help first. "
            "Please tell me what is not working, and I will check available retention options for you."
        )

    if known_customer:
        return (
            "Thank you. I already have your account details in this call context. "
            "Please tell me the exact issue you want to resolve right now, and I will continue immediately."
        )

    return (
        "Thank you for the details. "
        "Please confirm your full name and registered phone number so I can verify your account and assist you quickly."
    )


def _fallback_intent(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ["bill", "charge", "invoice", "refund", "payment", "charged"]):
        return "billing_dispute"
    if any(w in t for w in ["signal", "network", "outage", "slow", "internet", "connection"]):
        return "network_outage"
    if any(w in t for w in ["upgrade", "more data", "better plan", "unlimited"]):
        return "plan_upgrade"
    if any(w in t for w in ["cancel", "leave", "switch", "quit"]):
        return "churn_risk"
    if any(w in t for w in ["sim", "replace", "lost", "stolen", "esim"]):
        return "sim_swap"
    return "account_query"


def _fallback_sentiment(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ["angry", "furious", "worst", "terrible", "useless"]):
        return "angry"
    if any(w in t for w in ["frustrated", "annoyed", "still", "again", "never fixed"]):
        return "frustrated"
    if any(w in t for w in ["thank", "great", "happy", "appreciate"]):
        return "happy"
    return "neutral"


def _fallback_urgency(text: str, sentiment: str) -> str:
    t = (text or "").lower()
    if "urgent" in t or "angry" in t or "worst" in t or sentiment == "angry":
        return "high"
    if sentiment == "frustrated" or any(w in t for w in ["again", "still", "since morning", "waiting"]):
        return "medium"
    return "low"


def _state_guard_response(state: dict, response_text: str) -> str:
    """Prevent repeated requests when critical details are already captured."""
    text = (response_text or "").strip()
    if state.get("postcode_received") and "postcode" in text.lower() and "thank" not in text.lower():
        return (
            "Thank you for sharing your postcode. "
            "I can see there may be a network issue in your area and I am checking it now."
        )
    return text


async def _call_llm(prompt: str, json_mode: bool = False) -> str:
    """Generic LLM caller supporting Ollama, Gemini, and OpenRouter."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 500},
                }
                response = await client.post(url, json=payload)
                response.raise_for_status()
                candidates = response.json().get("candidates", [])
                if not candidates:
                    return ""
                return candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()

            elif LLM_PROVIDER == "openrouter" and OPENROUTER_API_KEY:
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": OPENROUTER_SITE_URL,
                    "X-Title": OPENROUTER_APP_NAME,
                }
                payload = {
                    "model": DEFAULT_OPENROUTER_MODEL,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}],
                }
                response = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                choices = response.json().get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "").strip()

            elif LLM_PROVIDER == "groq" and GROQ_API_KEY:
                headers = {
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": DEFAULT_GROQ_MODEL,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}],
                }
                response = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                choices = response.json().get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "").strip()

            elif LLM_PROVIDER == "together" and TOGETHER_API_KEY:
                headers = {
                    "Authorization": f"Bearer {TOGETHER_API_KEY}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": DEFAULT_TOGETHER_MODEL,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}],
                }
                response = await client.post("https://api.together.xyz/v1/chat/completions", json=payload, headers=headers)
                response.raise_for_status()
                choices = response.json().get("choices", [])
                if not choices:
                    return ""
                return choices[0].get("message", {}).get("content", "").strip()


            else:  # Default to Ollama
                model = await _resolve_ollama_model()
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}
                }
                response = await client.post(OLLAMA_URL, json=payload)
                response.raise_for_status()
                return (response.json().get("response", "") or "").strip()

    except Exception as e:
        print(f"LLM call failed ({LLM_PROVIDER}): {e}")
        return ""


async def get_ai_response(
    messages: list,
    customer: Optional[dict] = None,
) -> dict:
    """
    Generate AI response using RAG-grounded prompt.
    Returns dict with response, intent, sentiment, urgency, and rag_sources.
    """
    latest_customer_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            latest_customer_text = (msg.get("content") or "").strip()
            break

    intent = _fallback_intent(latest_customer_text)
    sentiment = _fallback_sentiment(latest_customer_text)
    urgency = _fallback_urgency(latest_customer_text, sentiment)

    prompt, retrieved_kb = build_rag_prompt(
        customer_message=latest_customer_text,
        customer=customer,
        conversation_history=messages,
        client_id="telecorp"
    )

    rag_sources = get_rag_context_for_display(latest_customer_text)

    reply = await _call_llm(prompt)
    if not reply:
        reply = _fallback_agent_response(latest_customer_text, customer)

    return {
        "response": reply,
        "intent": intent,
        "sentiment": sentiment,
        "urgency": urgency,
        "rag_sources": rag_sources,
    }


async def get_contextual_ai_response(
    current_input: str,
    conversation_history: list,
    state: dict,
    customer_info: Optional[dict] = None,
    memory: Optional[list] = None,
) -> dict:
    """Context-aware structured response with state tracking support."""
    customer_block = "name: unknown, plan: unknown"
    if customer_info:
        customer_block = f"name: {customer_info.get('name', 'unknown')}, plan: {customer_info.get('plan', 'unknown')}"

    memory_block = "No previous issues"
    if memory:
        memory_block = "\n".join(memory[:3])

    history_block = "\n".join(conversation_history[-5:]) if conversation_history else "No previous conversation"
    known_customer = _is_customer_known(customer_info)

    prompt = f"""You are Sarah, a telecom customer support AI.

RULES:
- Always use conversation history.
- Do NOT ask user to repeat information already provided.
- If Customer Info is present, treat identity as already verified for this active call.
- Do NOT ask for full name, address, age, email, or phone again unless Customer Info is missing.
- If user gives details (postcode, issue), use them immediately.
- Continue conversation naturally.
- Be empathetic if sentiment is negative.

Customer Info:
{customer_block}

Previous Issues:
{memory_block}

System State:
- Postcode requested: {state.get('postcode_requested', False)}
- Postcode received: {state.get('postcode_received', False)}
- Issue identified: {state.get('issue_identified', False)}
- Known customer: {known_customer}
- Verification complete: {state.get('verification_complete', known_customer)}

Conversation History:
{history_block}

Current Message:
{current_input}

Tasks:
1. Understand full context
2. Identify intent
3. Detect sentiment (happy, neutral, frustrated, angry, abusive)
4. Detect urgency (low, medium, high)
5. Generate response (1-2 lines, no repetition)

Return JSON only:
{{
  "response": "",
  "intent": "",
  "sentiment": "",
  "urgency": "",
  "confidence": 0
}}"""

    raw = await _call_llm(prompt, json_mode=True)
    parsed = _extract_json_payload(raw)

    if not parsed:
        parsed = {
            "response": _fallback_agent_response(current_input, customer_info),
            "intent": _fallback_intent(current_input),
            "sentiment": _fallback_sentiment(current_input),
            "urgency": _fallback_urgency(current_input, _fallback_sentiment(current_input)),
            "confidence": 58,
        }

    sentiment = str(parsed.get("sentiment", "neutral")).lower()
    urgency = str(parsed.get("urgency", "low")).lower()

    lower_input = (current_input or "").lower()
    if "frustrated" in lower_input:
        sentiment = "frustrated"
    if "angry" in lower_input or "worst" in lower_input or "urgent" in lower_input:
        urgency = "high"
    elif urgency not in ["low", "medium", "high"]:
        urgency = _fallback_urgency(lower_input, sentiment)

    response_text = _state_guard_response(state, str(parsed.get("response", "")).strip())
    if known_customer and _is_reverification_request(response_text):
        response_text = _fallback_agent_response(current_input, customer_info)
    if not response_text:
        response_text = _fallback_agent_response(current_input, customer_info)

    return {
        "response": response_text,
        "intent": str(parsed.get("intent", _fallback_intent(current_input))),
        "sentiment": sentiment,
        "urgency": urgency,
        "confidence": int(parsed.get("confidence", 60)) if str(parsed.get("confidence", "")).isdigit() else 60,
    }


async def analyze_message(message: str) -> dict:
    """Analyze a message for intent and sentiment."""
    prompt = f"""Analyze this customer message and respond with ONLY a JSON object (no other text):

Message: "{message}"

Return exactly this format:
{{"intent": "billing/recharge/network/plan/complaint/inquiry/greeting/other", "sentiment": "positive/neutral/negative/angry", "urgency": "low/medium/high"}}"""

    raw = await _call_llm(prompt, json_mode=True)
    parsed = _extract_json_payload(raw)
    if parsed:
        return parsed
    return {"intent": "other", "sentiment": "neutral", "urgency": "medium"}


async def generate_call_summary(
    transcript: list,
    customer_history: str = ""
) -> dict:
    """Generate post-call summary using full transcript."""
    if not transcript or len(transcript) < 2:
        return {
            "summary": "Call ended before sufficient conversation.",
            "issue": _infer_issue_from_transcript(transcript),
            "sentiment": "neutral",
            "resolution": "unresolved",
            "recommended_action": "Manual review required",
        }

    transcript_text = ""
    for msg in transcript:
        role = msg.get("role") or ("user" if msg.get("speaker") == "customer" else "assistant")
        content = msg.get("content") or msg.get("message") or ""
        transcript_text += f"{'Customer' if role == 'user' else 'Agent'}: {content}\n"

    prompt = f"""Analyse this customer service call transcript and return ONLY a JSON object.
No explanation, no markdown, just raw JSON.

Customer history:
{customer_history if customer_history else 'No previous issues'}

TRANSCRIPT:
{transcript_text}

Return this exact JSON structure:
{{
    "summary": "2 sentence description of what happened on this call",
    "issue": "one of: billing_dispute, network_outage, plan_upgrade, plan_downgrade, churn_risk, collections_payment, technical_support, number_porting, sim_swap, roaming_query, account_query, complaint_formal, other",
    "sentiment": "one of: positive, neutral, frustrated, angry",
    "resolution": "one of: resolved, unresolved, escalated, callback_required",
    "recommended_action": "one specific action the agent should take next"
}}"""

    raw = await _call_llm(prompt, json_mode=True)
    parsed = _extract_json_payload(raw)
    if parsed:
        return {
            "summary": parsed.get("summary", "Call completed."),
            "issue": _normalize_summary_issue(parsed.get("issue"), transcript),
            "sentiment": parsed.get("sentiment", "neutral"),
            "resolution": _normalize_summary_resolution(parsed.get("resolution")),
            "recommended_action": parsed.get("recommended_action", "Manual review required"),
        }

    return {
        "summary": "Call completed.",
        "issue": _infer_issue_from_transcript(transcript),
        "sentiment": "neutral",
        "resolution": "unresolved",
        "recommended_action": "Manual review required",
    }


async def check_ollama_status() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            return response.status_code == 200
    except Exception:
        return False
