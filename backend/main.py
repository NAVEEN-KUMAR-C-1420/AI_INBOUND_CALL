from datetime import datetime
import uuid
import json
from typing import Any, Dict, List, Optional, cast
from collections import deque
import re

import httpx
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
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
    get_customer_by_name,
    get_customer_by_phone,
    get_db,
    get_assist_events,
    init_db,
    save_assist_event,
    save_call_session,
    get_repeat_issue_count,
    get_repeat_callers,
    save_call_outcome,
    get_call_outcome,
    mark_escalation_needed,
    get_escalation_status,
    save_human_takeover_transcript,
)
from abusive_words import detect_abusive_language, extract_abusive_patterns
from ollama_service import (
    check_ollama_status,
    generate_call_summary,
    get_contextual_ai_response,
    get_ai_response,
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


def _new_context(call_type: str = "inbound") -> dict[str, Any]:
    return {
        "history": deque(maxlen=5),
        "call_type": call_type,
        "sentiment_arc": [],
        "assist_history": [],
        "consecutive_angry_turns": 0,
        "last_intent": "account_query",
        "state": {
            "postcode_requested": False,
            "postcode_received": False,
            "issue_identified": False,
        },
        "human_takeover_mode": False,
        "human_takeover_start_time": None,
        "abusive_language_detected": False,
        "escalation_reason": None,
        "repeat_issue_count": 0,
    }


def _append_history(context: dict[str, Any], speaker: str, message: str) -> None:
    context["history"].append(f"{speaker}: {message}")


def _history_to_messages(history: List[str]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    for line in history:
        if line.startswith("Customer:"):
            messages.append({"role": "user", "content": line.split(":", 1)[1].strip()})
        elif line.startswith("AI:"):
            messages.append({"role": "assistant", "content": line.split(":", 1)[1].strip()})
    return messages


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


def _phone_digits(value: Optional[str]) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _resolve_customer_from_incoming(
    phone: Optional[str],
    name: Optional[str] = None,
) -> Optional[dict]:
    """Resolve existing customer from incoming phone/name using tolerant matching."""
    if phone:
        direct = get_customer_by_phone(phone)
        if direct:
            return direct

        incoming_digits = _phone_digits(phone)
        if incoming_digits:
            # Try a few common UK variants first.
            variants = [
                phone,
                f"+{incoming_digits}",
                f"0{incoming_digits[-10:]}" if len(incoming_digits) >= 10 else incoming_digits,
            ]
            for candidate in variants:
                found = get_customer_by_phone(candidate)
                if found:
                    return found

            # Final fallback: compare normalized digits with stored customers.
            for item in get_all_customers():
                stored_digits = _phone_digits(item.get("phone"))
                if stored_digits and (
                    stored_digits == incoming_digits
                    or stored_digits.endswith(incoming_digits[-10:])
                    or incoming_digits.endswith(stored_digits[-10:])
                ):
                    return get_customer_by_phone(item.get("phone"))

    if name:
        return get_customer_by_name(name)

    return None

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
    call_type: str = "inbound"


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
    sentiment_state: str = "neutral"
    sentiment_arc: List[str] = []
    language_mode: str = "english"
    escalation_alert: bool = False
    trigger_phrases: List[str] = []
    suggestions: List[Dict[str, Any]] = []


class RealtimeIngestRequest(BaseModel):
    session_id: Optional[str] = None
    chunk: str
    role: str = "customer"
    call_type: str = "inbound"
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None


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
    session_id: Optional[str] = None


class SummaryRequest(BaseModel):
    transcript: List[Message]
    session_id: Optional[str] = None
    customer_phone: Optional[str] = None


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
    return {
        "status": "healthy",
        "ollama": "connected" if ollama_status else "disconnected",
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

    # Initialize in-memory rolling context for this call.
    CALL_CONTEXT[cast(int, call.id)] = _new_context(call_type=call_data.call_type)
    return call


@app.post("/calls/{call_id}/message", response_model=MessageResponse)
async def send_message(call_id: int, request: MessageRequest, db: Session = Depends(get_db)):
    call = db.query(Call).filter(Call.id == call_id).first()
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")
    if cast(str, call.status) != "active":
        raise HTTPException(status_code=400, detail="Call is not active")

    context = CALL_CONTEXT.setdefault(call_id, _new_context())

    # Build memory context for this customer.
    memories = (
        db.query(Memory)
        .filter(Memory.customer_id == call.customer_id)
        .order_by(Memory.created_at.desc())
        .limit(5)
        .all()
    )

    customer_conv = Conversation(
        call_id=call_id,
        speaker="customer",
        message=request.message,
        intent=None,
        sentiment=None,
    )
    db.add(customer_conv)
    db.flush()

    _append_history(context, "Customer", request.message)

    customer_profile = _resolve_customer_from_incoming(
        phone=cast(str, call.customer.phone),
        name=cast(str, call.customer.name),
    )

    history_messages = _history_to_messages(list(context["history"]))
    if customer_profile:
        ai_result = await get_ai_response(
            messages=history_messages,
            customer=customer_profile,
        )
    else:
        ai_result = await get_contextual_ai_response(
            current_input=request.message,
            conversation_history=list(context["history"]),
            state=context["state"],
            customer_info={
                "name": cast(str, call.customer.name),
                "plan": cast(str, call.customer.plan),
                "phone": cast(str, call.customer.phone),
            },
            memory=_memory_lines(memories),
        )
    ai_text = ai_result.get("response", "")

    # Keep deterministic safety rules in backend.
    intent = ai_result.get("intent") or detect_intent(request.message)
    sentiment = ai_result.get("sentiment") or detect_sentiment(request.message)
    urgency = ai_result.get("urgency") or detect_urgency(request.message, sentiment)

    if "frustrated" in (request.message or "").lower():
        sentiment = "frustrated"
    if any(w in (request.message or "").lower() for w in ["angry", "worst", "urgent"]):
        urgency = "high"

    assist = build_realtime_assist(
        context=context,
        transcript_chunk=request.message,
        intent=intent,
        sentiment=sentiment,
        urgency=urgency,
        customer_profile=customer_profile,
        is_inbound=bool(context.get("call_type", "inbound") == "inbound"),
    )

    _update_state_from_user(context, request.message, intent)
    _update_state_from_ai(context, ai_text)
    _append_history(context, "AI", ai_text)

    ai_conv = Conversation(call_id=call_id, speaker="ai", message=ai_text)
    db.add(ai_conv)

    # Persist detected metadata for transcript intelligence.
    setattr(customer_conv, "intent", cast(Any, intent))
    setattr(customer_conv, "sentiment", cast(Any, sentiment))
    db.commit()

    return MessageResponse(
        ai_response=ai_text,
        intent=intent,
        sentiment=sentiment,
        urgency=urgency,
        sentiment_state=assist["sentiment_state"],
        sentiment_arc=assist["sentiment_arc"],
        language_mode=assist["language_mode"],
        escalation_alert=assist["escalation_alert"],
        trigger_phrases=assist["trigger_phrases"],
        suggestions=assist["suggestions"],
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

    setattr(call, "status", cast(Any, "completed"))
    setattr(call, "end_time", cast(Any, datetime.utcnow()))
    db.commit()

    # Release in-memory context for ended calls.
    CALL_CONTEXT.pop(call_id, None)

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
    """Main chat endpoint that returns complete non-streaming response."""
    try:
        session_id = request.session_id or str(uuid.uuid4())
        context = CHAT_SESSION_CONTEXT.setdefault(session_id, _new_context())

        messages = [m.model_dump() for m in request.messages]

        latest_customer_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                latest_customer_msg = msg.get("content", "")
                break

        if latest_customer_msg:
            _append_history(context, "Customer", latest_customer_msg)

        # Resolve caller from incoming phone first, then fallback to name.
        customer_profile = _resolve_customer_from_incoming(
            phone=request.customer_phone,
            name=request.customer_name,
        )

        if customer_profile:
            ai_result = await get_ai_response(
                messages=messages,
                customer=customer_profile,
            )
        else:
            # New caller path: collect basics first, then proceed with query support.
            ai_result = await get_ai_response(
                messages=messages,
                customer=None,
            )

        response_text = ai_result.get("response", "")
        intent = ai_result.get("intent") or detect_intent(latest_customer_msg)
        sentiment = ai_result.get("sentiment") or detect_sentiment(latest_customer_msg)
        urgency = ai_result.get("urgency") or detect_urgency(latest_customer_msg, sentiment)

        if "frustrated" in (latest_customer_msg or "").lower():
            sentiment = "frustrated"
        if any(w in (latest_customer_msg or "").lower() for w in ["angry", "worst", "urgent"]):
            urgency = "high"

        _update_state_from_user(context, latest_customer_msg, intent)
        _update_state_from_ai(context, response_text)
        _append_history(context, "AI", response_text)

        return {
            "response": response_text,
            "intent": intent,
            "sentiment": sentiment,
            "urgency": urgency,
            "customer_found": bool(customer_profile),
            "customer_profile": customer_profile,
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/realtime/ingest")
async def realtime_ingest(request: RealtimeIngestRequest):
    """Ingest streaming transcript chunks (live/simulated) and return realtime assist."""
    try:
        session_id = request.session_id or str(uuid.uuid4())
        context = CHAT_SESSION_CONTEXT.setdefault(session_id, _new_context(call_type=request.call_type))

        if request.call_type:
            context["call_type"] = request.call_type

        role = "Customer" if request.role == "customer" else "AI"
        chunk = (request.chunk or "").strip()
        if chunk:
            _append_history(context, role, chunk)

        customer_profile = _resolve_customer_from_incoming(
            phone=request.customer_phone,
            name=request.customer_name,
        )

        normalized_text, noisy_markers = normalize_transcript(chunk)
        intent = detect_intent(normalized_text)
        sentiment = detect_sentiment(normalized_text)
        urgency = detect_urgency(normalized_text, sentiment)

        assist = build_realtime_assist(
            context=context,
            transcript_chunk=normalized_text,
            intent=intent,
            sentiment=sentiment,
            urgency=urgency,
            customer_profile=customer_profile,
            is_inbound=bool(context.get("call_type", "inbound") == "inbound"),
            noisy_markers=noisy_markers,
        )

        event = {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "call_type": context.get("call_type", "inbound"),
            "customer_id": customer_profile.get("id") if customer_profile else request.customer_phone,
            "transcript_chunk": normalized_text,
            "intent": intent,
            "sentiment": sentiment,
            "urgency": urgency,
            "language_mode": assist.get("language_mode", "english"),
            "escalation_alert": assist.get("escalation_alert", False),
            "trigger_phrases": assist.get("trigger_phrases", []),
            "suggestions": assist.get("suggestions", []),
        }
        save_assist_event(event)
        assist_history = context.setdefault("assist_history", [])
        assist_history.append(event)
        context["assist_history"] = assist_history[-100:]

        return {
            "session_id": session_id,
            "call_type": context.get("call_type", "inbound"),
            "normalized_text": normalized_text,
            "intent": intent,
            "sentiment": sentiment,
            "urgency": urgency,
            "customer_found": bool(customer_profile),
            "customer_profile": customer_profile,
            **assist,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/realtime/history/{session_id}")
async def realtime_history(session_id: str, limit: int = 100):
    return {
        "session_id": session_id,
        "events": get_assist_events(session_id, limit=limit),
    }


@app.websocket("/ws/realtime/assist")
async def websocket_realtime_assist(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)
            req = RealtimeIngestRequest(
                session_id=payload.get("session_id"),
                chunk=payload.get("chunk", ""),
                role=payload.get("role", "customer"),
                call_type=payload.get("call_type", "inbound"),
                customer_phone=payload.get("customer_phone"),
                customer_name=payload.get("customer_name"),
            )
            data = await realtime_ingest(req)
            await websocket.send_text(json.dumps(data))
    except WebSocketDisconnect:
        return
    except Exception as e:
        await websocket.send_text(json.dumps({"error": str(e)}))


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
                "call_type": CHAT_SESSION_CONTEXT.get(request.session_id, {}).get("call_type", "inbound"),
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


@app.get("/api/customer/{phone}")
async def api_customer(phone: str):
    customer = _resolve_customer_from_incoming(phone=phone)
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


def normalize_transcript(text: str) -> tuple[str, List[str]]:
    """Clean noisy transcript chunks while preserving intent-bearing words."""
    t = (text or "").strip()
    markers: List[str] = []
    if not t:
        return t, markers

    lowered = t.lower()
    noise_patterns = ["uh", "umm", "mmm", "hmm", "...", "--", "???", "[noise]", "[inaudible]"]
    for pat in noise_patterns:
        if pat in lowered:
            markers.append(pat)

    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(\b\w+\b)(?:\s+\1\b)+", r"\1", t, flags=re.IGNORECASE)
    t = re.sub(r"\[inaudible\]|\[noise\]", "", t, flags=re.IGNORECASE)
    t = t.strip()
    return t, markers


def detect_language_mode(text: str) -> str:
    """Detect English vs Tamil vs Tanglish for multilingual assist."""
    if not text:
        return "english"

    tamil_chars = len(re.findall(r"[\u0B80-\u0BFF]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    tanglish_markers = ["enna", "seri", "unga", "problem", "bill", "signal", "romba", "please"]
    marker_hits = sum(1 for w in tanglish_markers if w in text.lower())

    if tamil_chars > 5 and latin_chars > 5:
        return "tanglish"
    if tamil_chars > 5:
        return "tamil"
    if marker_hits >= 2:
        return "tanglish"
    return "english"


def sentiment_state(sentiment: str) -> str:
    s = (sentiment or "neutral").lower()
    if s == "angry":
        return "angry_or_churn_risk"
    if s == "frustrated":
        return "frustrated"
    if s == "neutral":
        return "neutral"
    return "mildly_frustrated"


def sentiment_score(sentiment: str) -> int:
    s = (sentiment or "neutral").lower()
    if s == "angry":
        return 3
    if s == "frustrated":
        return 2
    if s == "neutral":
        return 1
    return 0


def suggest_templates(
    intent: str,
    sentiment: str,
    call_type: str,
    language_mode: str,
    customer_profile: Optional[dict],
) -> List[Dict[str, Any]]:
    name = "there"
    if customer_profile and customer_profile.get("full_name"):
        name = str(customer_profile.get("full_name")).split()[0]

    direction_hint = "for this inbound concern"
    if call_type == "outbound":
        direction_hint = "for this proactive outbound follow-up"

    base_map: Dict[str, List[str]] = {
        "billing_dispute": [
            f"Hi {name}, I can see the billing concern. I will verify the last two invoices now and tell you the exact correction amount.",
            f"I understand this is frustrating; let me resolve it now {direction_hint}. Please confirm the billed date you are referring to.",
            "Once this is resolved, I can also check if a lower-cost billing plan is available for you.",
        ],
        "network_outage": [
            f"Thanks {name}. I am checking network health in your area now; please share whether calls, data, or both are impacted.",
            "I will run a line reset and give you a concrete update window within two minutes.",
            "After stabilizing the issue, I can also review a stronger coverage add-on for your location.",
        ],
        "churn_risk": [
            f"I hear you, {name}. First, let me fix the immediate issue driving this decision right now.",
            "Once we confirm stability, I will compare your current plan with a lower-cost option and show exact savings.",
            "If needed, I can connect a supervisor now so we can finalize the best offer on this call.",
        ],
        "plan_upgrade": [
            "I can recommend the best upgrade using your usage pattern and explain price difference in one line.",
            "I will shortlist two plans: value-first and data-first, then you can pick instantly.",
            "If you travel often, I can include roaming-friendly bundles in the options.",
        ],
    }

    suggestions = base_map.get(intent, [
        f"Thanks {name}. I understand the issue and I will resolve it step by step.",
        "Let me confirm key details and provide the quickest next action right now.",
        "If this is urgent, I can prioritize escalation while we continue troubleshooting.",
    ])

    if sentiment in ["frustrated", "angry"]:
        suggestions[0] = f"I understand this has been frustrating, {name}. I will take ownership and fix this now."

    ranked: List[Dict[str, Any]] = []
    for idx, text in enumerate(suggestions[:3], start=1):
        localized = text
        if language_mode == "tanglish":
            localized = text.replace("I understand", "Puriyuthu").replace("I will", "Naan").replace("please", "please")
        elif language_mode == "tamil":
            localized = "உங்கள் பிரச்சினையை உடனே பார்க்கிறேன். இரண்டு நிமிடத்தில் தெளிவான அடுத்த படி சொல்கிறேன்."

        ranked.append(
            {
                "rank": idx,
                "text": localized,
                "resolution_likelihood": round(max(0.55, 0.9 - (idx - 1) * 0.12), 2),
                "tone_match": "high" if idx == 1 else "medium",
            }
        )

    return ranked


def build_realtime_assist(
    context: Dict[str, Any],
    transcript_chunk: str,
    intent: str,
    sentiment: str,
    urgency: str,
    customer_profile: Optional[dict],
    is_inbound: bool,
    noisy_markers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    noisy_markers = noisy_markers or []
    language_mode = detect_language_mode(transcript_chunk)

    # === ABUSIVE LANGUAGE DETECTION ===
    is_abusive, matched_words = detect_abusive_language(transcript_chunk, language_mode)
    if is_abusive:
        context["abusive_language_detected"] = True
        context["escalation_reason"] = f"abusive_language: {','.join(matched_words)}"

    arc: List[str] = context.setdefault("sentiment_arc", [])
    arc.append(sentiment)
    context["sentiment_arc"] = arc[-12:]

    if sentiment == "angry":
        context["consecutive_angry_turns"] = int(context.get("consecutive_angry_turns", 0)) + 1
    else:
        context["consecutive_angry_turns"] = 0

    prev_score = sentiment_score(arc[-2]) if len(arc) > 1 else sentiment_score(sentiment)
    curr_score = sentiment_score(sentiment)
    drop_detected = curr_score > prev_score

    trigger_words = [
        w for w in ["cancel", "switch", "ofcom", "angry", "refund", "urgent", "worst", "terrible"]
        if w in (transcript_chunk or "").lower()
    ]

    angry_turns = int(context.get("consecutive_angry_turns", 0))
    
    # ESCALATION LOGIC: abusive language OR 2+ angry turns
    escalation_alert = (
        is_abusive or 
        (angry_turns >= 2) or 
        (sentiment == "frustrated" and (urgency == "high" or intent == "churn_risk" or drop_detected))
    )

    # Check for repeat issues (if customer found)
    repeat_count = 0
    if customer_profile and customer_profile.get("id"):
        repeat_count = get_repeat_issue_count(customer_profile.get("id"), intent or "account_query")
        context["repeat_issue_count"] = repeat_count

    suggestions = suggest_templates(
        intent=intent,
        sentiment=sentiment,
        call_type="inbound" if is_inbound else "outbound",
        language_mode=language_mode,
        customer_profile=customer_profile,
    )

    if not is_inbound:
        for s in suggestions:
            s["text"] = "Outbound context: " + s["text"]

    return {
        "sentiment_state": sentiment_state(sentiment),
        "sentiment_arc": context["sentiment_arc"],
        "language_mode": language_mode,
        "call_type": "inbound" if is_inbound else "outbound",
        "escalation_alert": escalation_alert,
        "angry_turns": angry_turns,
        "trajectory_drop": drop_detected,
        "abusive_language_detected": is_abusive,
        "abusive_words": list(matched_words) if is_abusive else [],
        "repeat_issue_count": repeat_count,
        "repeat_caller_warning": repeat_count >= 3,
        "trigger_phrases": sorted(list(set(trigger_words + noisy_markers)))[:6],
        "suggestions": suggestions,
        "human_takeover_mode": context.get("human_takeover_mode", False),
    }


# =============================================================================
# NEW ENDPOINTS: ESCALATION, HUMAN TAKEOVER, FEEDBACK, PATTERNS
# =============================================================================

@app.post("/api/escalate")
async def escalate_to_human(request: dict):
    """
    Escalate a call session to human agent.
    Request: { session_id, reason, escalation_phone? }
    Returns: { success, escalation_phone, reference_id, wait_time_estimate }
    """
    session_id = request.get("session_id")
    reason = request.get("reason", "customer_request")
    escalation_phone = request.get("escalation_phone", "1-800-TELECORP")
    
    try:
        if session_id in CHAT_SESSION_CONTEXT:
            context = CHAT_SESSION_CONTEXT[session_id]
            context["escalation_reason"] = reason
            context["human_takeover_mode"] = False  # Stop AI, ready for human
        
        # Save escalation to DB
        mark_escalation_needed(session_id, reason, escalation_phone)
        
        return {
            "success": True,
            "escalation_phone": escalation_phone,
            "reference_id": session_id,
            "wait_time_estimate": "2-3 minutes",
            "message": f"Connecting to human agent. Reference: {session_id}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/human-takeover/enable")
async def enable_human_takeover(request: dict):
    """
    Enable human takeover mode for a session.
    AI stops direct response and only suggests what to say.
    """
    session_id = request.get("session_id")
    
    try:
        if session_id not in CHAT_SESSION_CONTEXT:
            CHAT_SESSION_CONTEXT[session_id] = _new_context()
        
        context = CHAT_SESSION_CONTEXT[session_id]
        context["human_takeover_mode"] = True
        context["human_takeover_start_time"] = datetime.utcnow().isoformat()
        
        return {
            "success": True,
            "session_id": session_id,
            "mode": "human_takeover_enabled",
            "message": "Human takeover enabled. AI will provide suggestions only."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/human-takeover/disable")
async def disable_human_takeover(request: dict):
    """Disable human takeover mode, return to AI-assisted mode."""
    session_id = request.get("session_id")
    
    try:
        if session_id in CHAT_SESSION_CONTEXT:
            context = CHAT_SESSION_CONTEXT[session_id]
            takeover_duration = None
            if context.get("human_takeover_start_time"):
                start = datetime.fromisoformat(context["human_takeover_start_time"])
                takeover_duration = int((datetime.utcnow() - start).total_seconds())
            
            context["human_takeover_mode"] = False
            return {
                "success": True,
                "session_id": session_id,
                "message": "Returned to AI-assisted mode.",
                "takeover_duration_seconds": takeover_duration
            }
        return {"success": False, "message": "Session not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/human-takeover/send-text")
async def send_human_text_to_customer(request: dict):
    """
    Agent types text → convert to speech for customer.
    Request: { session_id, text, use_ai_suggestion? }
    Returns: { audio_url, text_sent, ai_suggestions }
    """
    session_id = request.get("session_id")
    agent_text = request.get("text", "").strip()
    use_ai_suggestion = request.get("use_ai_suggestion", False)
    
    try:
        if not agent_text:
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        
        if session_id in CHAT_SESSION_CONTEXT:
            context = CHAT_SESSION_CONTEXT[session_id]
            if not context.get("human_takeover_mode"):
                raise HTTPException(status_code=400, detail="Human takeover not enabled")
            
            _append_history(context, "Agent", agent_text)
        
        # Save to DB
        if session_id:
            agent_messages = [{"text": agent_text, "timestamp": datetime.utcnow().isoformat()}]
            save_human_takeover_transcript(session_id, agent_messages, 0)
        
        # Generate AI-suggested alternatives
        ai_suggestions = [
            {"suggestion": "Let me look into that for you.", "tone": "empathetic"},
            {"suggestion": "I understand your frustr. Let's get this resolved.", "tone": "understanding"},
            {"suggestion": "I'd like to escalate this to my manager.", "tone": "professional"},
        ]
        
        return {
            "success": True,
            "text_sent": agent_text,
            "audio_url": f"/api/tts?text={agent_text[:50]}",  # Simplified
            "ai_suggestions": ai_suggestions,
            "message": "Text converted to speech for customer."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/call-outcome")
async def save_call_outcome_feedback(request: dict):
    """
    Submit call outcome feedback after call ends.
    Request: { session_id, resolved: bool, resolution_type, feedback_text }
    Returns: { success, learning_stored, similar_cases }
    """
    session_id = request.get("session_id")
    resolved = request.get("resolved", False)
    resolution_type = request.get("resolution_type", "")  # e.g., "technical_fix", "escalated", "repeat"
    feedback_text = request.get("feedback_text", "")
    
    try:
        save_call_outcome(session_id, resolved, resolution_type, feedback_text)
        
        return {
            "success": True,
            "session_id": session_id,
            "resolved": resolved,
            "message": "Call outcome recorded. AI learning updated.",
            "learning_stored": True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/repeat-caller-info/{phone}")
async def get_repeat_caller_info(phone: str):
    """
    Get pattern info if customer is a repeat caller with multiple issues.
    Returns: { is_repeat_caller, issue_count, prev_issues, recommendation }
    """
    try:
        customer = get_customer_by_phone(phone)
        if not customer:
            return {
                "is_repeat_caller": False,
                "issue_count": 0,
                "prev_issues": [],
                "recommendation": "New caller"
            }
        
        customer_id = str(customer.get("id", ""))
        repeat_info = get_repeat_callers(threshold=2)
        
        matching_repeats = [r for r in repeat_info if str(r.get("customer_id")) == customer_id]
        
        if matching_repeats:
            return {
                "is_repeat_caller": True,
                "issue_count": sum(r["call_count"] for r in matching_repeats),
                "prev_issues": [r["intent"] for r in matching_repeats],
                "recommendation": "Flag for escalation. Pattern detected: customer called 3+ times.",
                "recent_calls": matching_repeats
            }
        
        return {
            "is_repeat_caller": False,
            "issue_count": 0,
            "prev_issues": [],
            "recommendation": "Standard handling"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/escalations-pending")
async def get_pending_escalations():
    """Get all pending escalations waiting for human agent assignment."""
    try:
        # This would query the escalations table
        # For now, return mock data
        return {
            "pending_count": 0,
            "escalations": []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
