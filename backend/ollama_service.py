import httpx
import json
import re
from typing import Any, Optional

from config import get_kb
from database import get_customer_by_name, get_customer_by_phone, get_all_kb_context
from rag_service import build_rag_prompt, get_rag_context_for_display

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:3b"
FALLBACK_MODELS = [MODEL, "llama3.2:latest", "llama3", "qwen3:4b", "qwen2.5:3b", "mistral"]


async def _resolve_model() -> str:
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

    return MODEL


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


def _safe_parse_json(text: str) -> dict:
    """Safe JSON parser for summary responses with intelligent fallback."""
    if not text:
        return _create_fallback_summary()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback
    return _create_fallback_summary()


def _create_fallback_summary() -> dict:
    """Create fallback summary when parsing fails."""
    return {
        "summary": "Call completed.",
        "issue": "other",
        "sentiment": "neutral",
        "resolution": "unresolved",
        "recommended_action": "Manual review required",
    }


def _fallback_agent_response(user_text: str) -> str:
    """Deterministic fallback response when local model is unavailable."""
    text = (user_text or "").lower()

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

    return (
        "Thank you for the details. "
        "To continue, please share your full name, address, age, and email so I can verify your account and assist you quickly."
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


async def get_ai_response(
    messages: list,
    customer: Optional[dict] = None,
) -> dict:
    """
    Generate AI response using RAG-grounded prompt.
    Returns dict with response, intent, sentiment, urgency, and rag_sources.
    """
    # DEBUG — remove after fixing
    print("=== CUSTOMER RECEIVED BY AI ===")
    print(customer)
    print("================================")
    
    # Get the latest customer message
    latest_customer_text = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            latest_customer_text = (msg.get("content") or "").strip()
            break

    # Run local detection FIRST (fast)
    intent = _fallback_intent(latest_customer_text)
    sentiment = _fallback_sentiment(latest_customer_text)
    urgency = _fallback_urgency(latest_customer_text, sentiment)

    # Build RAG-grounded prompt
    prompt, retrieved_kb = build_rag_prompt(
        customer_message=latest_customer_text,
        customer=customer,
        conversation_history=messages,
        client_id="telecorp"
    )

    # Get RAG context for frontend display
    rag_sources = get_rag_context_for_display(latest_customer_text)

    # Build payload with RAG prompt
    payload = {
        "model": await _resolve_model(),
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 120,
            "num_ctx": 1024,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            reply = (data.get("response", "") or "").strip()
    except Exception as e:
        print(f"Ollama call failed: {e}")
        reply = _fallback_agent_response(latest_customer_text)

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
    selected_model = await _resolve_model()

    customer_block = "name: unknown, plan: unknown"
    if customer_info:
        customer_block = f"name: {customer_info.get('name', 'unknown')}, plan: {customer_info.get('plan', 'unknown')}"

    memory_block = "No previous issues"
    if memory:
        memory_block = "\n".join(memory[:3])

    history_block = "\n".join(conversation_history[-5:]) if conversation_history else "No previous conversation"

    prompt = f"""You are Sarah, a telecom customer support AI.

RULES:
- Always use conversation history.
- Do NOT ask user to repeat information already provided.
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

    payload = {
        "model": selected_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 180,
            "top_p": 0.9,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            raw = (response.json().get("response", "") or "").strip()
            parsed = _extract_json_payload(raw)

            if not parsed:
                parsed = {
                    "response": _fallback_agent_response(current_input),
                    "intent": _fallback_intent(current_input),
                    "sentiment": _fallback_sentiment(current_input),
                    "urgency": _fallback_urgency(current_input, _fallback_sentiment(current_input)),
                    "confidence": 58,
                }

            sentiment = str(parsed.get("sentiment", "neutral")).lower()
            urgency = str(parsed.get("urgency", "low")).lower()

            # Rule-based overrides requested for reliability.
            lower_input = (current_input or "").lower()
            if "frustrated" in lower_input:
                sentiment = "frustrated"
            if "angry" in lower_input or "worst" in lower_input or "urgent" in lower_input:
                urgency = "high"
            elif urgency not in ["low", "medium", "high"]:
                urgency = _fallback_urgency(lower_input, sentiment)

            response_text = _state_guard_response(state, str(parsed.get("response", "")).strip())
            if not response_text:
                response_text = _fallback_agent_response(current_input)

            return {
                "response": response_text,
                "intent": str(parsed.get("intent", _fallback_intent(current_input))),
                "sentiment": sentiment,
                "urgency": urgency,
                "confidence": int(parsed.get("confidence", 60)) if str(parsed.get("confidence", "")).isdigit() else 60,
            }
    except Exception as e:
        print(f"Contextual response fallback activated: {e}")
        sentiment = _fallback_sentiment(current_input)
        return {
            "response": _state_guard_response(state, _fallback_agent_response(current_input)),
            "intent": _fallback_intent(current_input),
            "sentiment": sentiment,
            "urgency": _fallback_urgency(current_input, sentiment),
            "confidence": 45,
        }


async def analyze_message(message: str) -> dict:
    """Analyze a message for intent and sentiment."""

    prompt = f"""Analyze this customer message and respond with ONLY a JSON object (no other text):

Message: "{message}"

Return exactly this format:
{{"intent": "billing/recharge/network/plan/complaint/inquiry/greeting/other", "sentiment": "positive/neutral/negative/angry", "urgency": "low/medium/high"}}"""

    selected_model = await _resolve_model()

    payload = {
        "model": selected_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 50
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            text = result.get("response", "").strip()

            parsed = _extract_json_payload(text)
            if parsed:
                return parsed

            return {"intent": "other", "sentiment": "neutral", "urgency": "medium"}
    except Exception:
        return {"intent": "other", "sentiment": "neutral", "urgency": "medium"}


async def generate_call_summary(
    transcript: list,
    customer_history: str = ""
) -> dict:
    """Generate post-call summary using full transcript with fallback logic."""

    if not transcript or len(transcript) < 2:
        return {
            "summary": "Call ended before sufficient conversation.",
            "issue": "other",
            "sentiment": "neutral",
            "resolution": "unresolved",
            "recommended_action": "Manual review required",
        }

    # Build full conversation text
    transcript_text = ""
    history_list = []
    for msg in transcript:
        role = msg.get("role") or ("user" if msg.get("speaker") == "customer" else "assistant")
        content = msg.get("content") or msg.get("message") or ""
        prefix = "Customer" if role == "user" else "Agent"
        line = f"{prefix}: {content}"
        transcript_text += line + "\n"
        history_list.append(line)

    # Build improved prompt
    prompt = f"""You are an AI call analyst.

Analyze the full conversation and generate structured output.

{customer_history if customer_history else 'No previous history'}

Full Conversation:
{transcript_text}

Tasks:
1. Summarize the issue in 1-2 sentences
2. Identify issue type (billing_dispute / network_outage / plan_upgrade / plan_downgrade / churn_risk / collections_payment / technical_support / number_porting / sim_swap / roaming_query / account_query / complaint_formal / other)
3. Detect final sentiment (positive / neutral / frustrated / angry)
4. Determine resolution status (resolved / unresolved / escalated)
5. Suggest next action (specific, actionable)
6. Decision (resolve / follow_up / escalate)

IMPORTANT:
Return ONLY valid JSON. No markdown, no explanation.

Format:
{{
  "summary": "",
  "issue": "",
  "sentiment": "",
  "resolution": "",
  "recommended_action": ""
}}"""

    selected_model = await _resolve_model()

    payload = {
        "model": selected_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 250,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            raw_text = result.get("response", "").strip()
            
            # DEBUG: print raw response
            print("===== SUMMARY RAW RESPONSE =====")
            print(raw_text)
            print("================================")
            
            # Clean markdown if present
            if raw_text.startswith("```"):
                raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            # Use safe parser
            parsed = _safe_parse_json(raw_text)

            return {
                "summary": parsed.get("summary", "Call completed."),
                "issue": parsed.get("issue", "other"),
                "sentiment": parsed.get("sentiment", "neutral"),
                "resolution": parsed.get("resolution", "unresolved"),
                "recommended_action": parsed.get("recommended_action", "Manual review required"),
            }
    except Exception as e:
        print(f"Exception during summary generation: {e}")
        return _create_fallback_summary()


async def check_ollama_status() -> bool:
    """Check if Ollama is running and accessible."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:11434/api/tags")
            return response.status_code == 200
    except Exception:
        return False


def build_system_prompt(customer_name: Optional[str] = None, customer_phone: Optional[str] = None) -> str:
    """Build a dynamic system prompt based on customer and knowledge base."""
    try:
        kb = get_kb()
    except Exception:
        kb = {}

    persona = kb.get("persona", {})
    company = kb.get("company", {})
    agent_name = persona.get("name", "Sarah")
    company_name = company.get("name", "TeleCorp UK")
    support_hours = company.get("support_hours", "Mon-Fri 9am-6pm")

    customer = None
    if customer_name:
        customer = get_customer_by_name(customer_name)
    if not customer and customer_phone:
        customer = get_customer_by_phone(customer_phone)

    if customer:
        risk = "HIGH - offer retention deal immediately" if float(customer.get("churn_risk_score") or 0) > 0.6 else "Normal"
        repeat = "YES - called 3+ times about same issue. Escalate if unresolved." if customer.get("repeat_issue") else "No"
        balance = (
            f"GBP {customer.get('outstanding_balance_gbp', 0)} OVERDUE"
            if float(customer.get("outstanding_balance_gbp") or 0) > 0
            else "None"
        )

        customer_block = f"""Name: {customer.get('full_name')}
Phone: {customer.get('phone')}
Plan: {customer.get('plan_name')} - GBP {customer.get('monthly_fee_gbp', 0)}/month
Account status: {customer.get('account_status', 'active')}
Outstanding balance: {balance}
Previous calls: {customer.get('call_history_count', 0)}
Last issue: {customer.get('last_call_intent', 'None')}
Churn risk: {risk}
Repeat issue flag: {repeat}"""
    else:
        caller_name = customer_name.strip() if customer_name else "Unknown caller"
        customer_block = (
            f"Caller name from incoming call: {caller_name}. "
            "No matching customer record found by name. "
            "Ask for these details politely: full name, address, age, and email."
        )

    try:
        kb_context = get_all_kb_context(limit=8)
    except Exception:
        kb_context = "Knowledge base unavailable."

    sign_off = persona.get('sign_off', 'Is there anything else I can help you with today?')

    prompt = f"""You are {agent_name}, a professional customer service agent for {company_name}.

CUSTOMER ON THIS CALL:
{customer_block}

HOW TO RESOLVE COMMON ISSUES:
{kb_context}

RULES:
1. Address the customer by name once you know it.
2. Identify their issue within 2 exchanges.
3. Give a specific resolution. Never say you are having technical difficulties.
4. If outstanding balance is overdue, offer a payment plan politely.
5. If churn risk is HIGH, offer a discount before the call ends.
6. If repeat issue is YES, apologise sincerely for the repeated problem.
7. Keep every response under 3 sentences.
8. End resolved calls with: "{sign_off}"

Respond only as {agent_name}. Never break character."""

    return prompt.strip()

# === END OF FILE: ollama_service.py ===
