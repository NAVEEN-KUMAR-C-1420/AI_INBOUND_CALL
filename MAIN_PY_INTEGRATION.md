# MAIN.PY INTEGRATION GUIDE

## Step 1: Add New Imports at Top

```python
# Add these imports to backend/main.py after existing imports:

from language_service import detect_language, get_response_language, get_system_prompt_language_instruction
from sentiment_service import detect_sentiment, get_sentiment_arc, get_de_escalation_suggestion, urgency_level
from outbound_service import start_outbound_call as start_outbound, process_customer_response as process_outbound_response, end_outbound_call
from memory_service import get_or_create_memory, end_call_memory, get_customer_pattern, get_customer_summary, cleanup_old_memories
from simulation_service import (
    get_available_scripts, start_simulation as start_sim,
    get_sim_session, get_next_sim_turn, submit_sim_analysis, end_simulation
)
```

---

## Step 2: Update Existing POST /api/chat Endpoint

Replace the existing `/api/chat` endpoint with this enhanced version:

```python
@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Enhanced chat endpoint with:
    - Multi-language detection & response routing
    - Sentiment analysis with trajectory
    - Memory & pattern tracking
    - Auto-escalation logic
    """
    session_id = request.session_id or str(uuid.uuid4())
    
    # Get or create call memory
    memory = get_or_create_memory(session_id, 
                                  request.customer.get("id") if request.customer else None)
    
    # Get last customer message
    customer_message = ""
    for msg in reversed(request.messages):
        if msg.get("role") == "user":
            customer_message = msg.get("content", "")
            break
    
    if not customer_message:
        return {
            "response": "Hello, how can I help you today?",
            "intent": "general",
            "sentiment": "neutral",
            "urgency": "low",
            "suggestions": [],
            "language": "en",
            "rag_sources": [],
            "escalation_needed": False
        }
    
    # 1. DETECT LANGUAGE
    detected_language = detect_language(customer_message)
    response_language = get_response_language(detected_language, request.language_history or [])
    
    # 2. DETECT SENTIMENT
    sentiment_result = detect_sentiment(customer_message, detected_language)
    
    # 3. UPDATE MEMORY
    memory.add_turn(
        role="user",
        content=customer_message,
        sentiment=sentiment_result.score,
        intent=sentiment_result.trigger_phrase,
        language=detected_language
    )
    
    # 4. COMPUTE SENTIMENT TRAJECTORY
    sentiment_result.trajectory = get_sentiment_arc(memory.sentiment_history)
    
    # 5. CALL EXISTING AI RESPONSE FUNCTION (from ollama_service)
    result = await get_ai_response(
        messages=[m.dict() for m in request.messages] if hasattr(request.messages[0], 'dict') else request.messages,
        customer=request.customer,
        session_language_history=request.language_history or []
    )
    
    # 6. UPDATE MEMORY WITH AI RESPONSE
    memory.add_turn(
        role="assistant",
        content=result.get("response", ""),
        language=response_language,
        suggestions=result.get("suggestions", [])
    )
    
    # 7. FORCE LANGUAGE INSTRUCTION INTO PROMPT if needed
    lang_instruction = get_system_prompt_language_instruction(response_language)
    
    # Add to result for frontend
    result["sentiment"] = sentiment_result.label
    result["sentiment_score"] = sentiment_result.score
    result["trajectory"] = sentiment_result.trajectory
    result["trigger_phrase"] = sentiment_result.trigger_phrase
    result["churn_risk"] = sentiment_result.churn_risk
    result["escalation_needed"] = sentiment_result.escalation_needed
    result["urgency"] = urgency_level(sentiment_result)
    result["language"] = response_language
    result["language_detected"] = detected_language
    result["memory_context"] = memory.get_context_for_prompt()
    
    # 8. AUTO-ESCALATION CHECK
    angry_turns = sum(1 for s in memory.sentiment_history if s < -0.7)
    abusive_detected = detect_abusive_language(customer_message)
    
    should_auto_escalate = (
        (sentiment_result.label == "angry" and angry_turns >= 2) or
        abusive_detected or
        sentiment_result.churn_risk
    )
    
    if should_auto_escalate:
        result["auto_escalated"] = True
        result["angry_turns"] = angry_turns
        memory.escalation_triggered = True
        # Mark for human takeover in frontend
    
    return result
```

---

## Step 3: Add NEW Endpoints

### Outbound Calls

```python
@app.post("/api/outbound/start")
async def start_outbound_call_endpoint(req: dict):
    """Start outbound call session."""
    customer_id = req.get("customer_id")
    call_type = req.get("call_purpose", "renewal")
    
    db = get_db()
    customer = get_customer_by_id(customer_id)
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    session = start_outbound(
        customer_id=customer_id,
        customer_name=customer.get("full_name", ""),
        call_type=call_type
    )
    
    return session


@app.post("/api/outbound/respond")
async def respond_to_outbound_call(req: dict):
    """Process customer response in outbound call."""
    session_id = req.get("session_id")
    response_text = req.get("response", "")
    
    result = process_outbound_response(session_id, response_text)
    return result


@app.post("/api/outbound/end")
async def end_outbound_call_endpoint(req: dict):
    """End outbound call session."""
    session_id = req.get("session_id")
    outcome = req.get("outcome", "partial")
    notes = req.get("notes", "")
    
    summary = end_outbound_call(session_id, outcome, notes)
    return summary


@app.get("/api/outbound/candidates")
async def get_outbound_call_candidates():
    """Get candidate customers for outbound calls."""
    db = get_db()
    customers = get_all_customers()
    
    candidates = {
        "renewal": [c for c in customers if c.get("contract_end") and is_renewal_due(c)],
        "upsell": [c for c in customers if c.get("upsell_score", 0) > 0.7],
        "collections": [c for c in customers if c.get("outstanding_balance_gbp", 0) > 0],
        "churn_win_back": [c for c in customers if c.get("churn_risk_score", 0) > 0.6],
    }
    
    return candidates
```

### Simulation

```python
@app.get("/api/scripts")
async def get_scripts():
    """Get available simulation scripts."""
    return get_available_scripts()


@app.post("/api/simulation/start")
async def start_simulation_endpoint(req: dict):
    """Start a simulation session."""
    script_id = req.get("script_id")
    
    result = start_sim(script_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result


@app.post("/api/simulation/next/{session_id}")
async def get_simulation_turn_endpoint(session_id: str, req: dict = None):
    """Get next turn in simulation."""
    turn_data = get_next_sim_turn(session_id)
    
    if turn_data.get("completed"):
        return turn_data
    
    # If customer turn, run AI analysis
    if turn_data.get("speaker") == "customer":
        # Get AI analysis of customer turn
        analysis_req: ChatRequest = ChatRequest(
            messages=[{"role": "user", "content": turn_data.get("text")}],
            customer=None,
            session_id=session_id
        )
        
        analysis = await chat(analysis_req)
        turn_data["ai_analysis"] = analysis
        
        # Add AI response as next turn
        script = get_sim_session(session_id)
        if script:
            script.advance_turn(analysis)
    
    return turn_data


@app.post("/api/simulation/end/{session_id}")
async def end_simulation_endpoint(session_id: str):
    """End simulation and return report."""
    report = end_simulation(session_id)
    return report
```

### Escalation Management

```python
@app.post("/api/escalation/resolve/{session_id}")
async def resolve_escalation_endpoint(session_id: str):
    """Restore AI control after human takeover."""
    # Get memory and clear escalation flag
    memory = get_or_create_memory(session_id)
    memory.escalation_triggered = False
    memory.human_takeover_active = False
    
    return {
        "status": "ai_restored",
        "session_id": session_id,
        "message": "AI control restored. Resuming automated assistance."
    }


@app.get("/api/escalation/status/{session_id}")
async def check_escalation_status(session_id: str):
    """Check escalation status of session."""
    memory = get_or_create_memory(session_id)
    
    return {
        "session_id": session_id,
        "escalated": memory.escalation_triggered,
        "human_takeover_active": memory.human_takeover_active
    }
```

### Analytics & Patterns

```python
@app.get("/api/customer-pattern/{customer_id}")
async def get_customer_pattern_endpoint(customer_id: str):
    """Get cross-call pattern for customer."""
    pattern = get_customer_pattern(customer_id)
    
    if not pattern:
        return {"message": "No pattern data yet"}
    
    return pattern


@app.get("/api/customer-summary/{customer_id}")
async def get_customer_summary_endpoint(customer_id: str):
    """Get comprehensive customer summary."""
    summary = get_customer_summary(customer_id)
    return summary
```

---

## Step 4: Schedule Cleanup Task (Optional)

Add before app startup:

```python
import asyncio

async def cleanup_task():
    """Periodically clean up old memories."""
    while True:
        await asyncio.sleep(3600)  # Every hour
        cleanup_old_memories(max_age_hours=24)


@app.on_event("startup")
async def startup():
    create_all_tables()
    rag_status = warmup_rag("telecorp")
    
    # Start cleanup task
    asyncio.create_task(cleanup_task())
    
    print("✅ System ready. Ollama:", "🟢 Connected" if check_ollama_status() else "🔴 Disconnected")
```

---

## Step 5: Update WebSocket Endpoint (if exists)

Add handling for new message types:

```python
@app.websocket("/ws/call/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    memory = get_or_create_memory(session_id)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "audio_chunk":
                # Handle streaming audio/interim transcript
                transcript = data.get("data", {}).get("transcript", "")
                memory.add_turn(role="user", content=transcript, language="en")
                
                # Send back interim analysis
                await websocket.send_json({
                    "type": "transcript_update",
                    "data": {"interim": transcript}
                })
            
            elif msg_type == "user_message":
                # Full user message
                message = data.get("data", {}).get("message", "")
                result = await chat(ChatRequest(
                    messages=[{"role": "user", "content": message}],
                    session_id=session_id
                ))
                
                await websocket.send_json({
                    "type": "ai_update",
                    "data": result
                })
            
            elif msg_type == "end_call":
                # End session
                memory_obj = end_call_memory(session_id)
                await websocket.send_json({
                    "type": "call_summary",
                    "data": {"message": "Call ended"}
                })
                break
            
            elif msg_type == "escalate":
                await websocket.send_json({
                    "type": "escalation",
                    "data": {"escalated": True}
                })
            
            elif msg_type == "restore_ai":
                memory.escalation_triggered = False
                await websocket.send_json({
                    "type": "ai_update",
                    "data": {"message": "AI control restored"}
                })
    
    except WebSocketDisconnect:
        print(f"WebSocket disconnected: {session_id}")
        end_call_memory(session_id)
```

---

## Step 6: Utility Functions to Add

```python
def is_renewal_due(customer: dict) -> bool:
    """Check if customer contract is due for renewal."""
    from datetime import datetime, timedelta
    
    contract_end = customer.get("contract_end")
    if not contract_end:
        return False
    
    contract_date = datetime.fromisoformat(contract_end)
    renewal_window = datetime.utcnow() + timedelta(days=30)
    
    return contract_date <= renewal_window

def is_new_intent(current: str, history: list) -> bool:
    """Check if current intent is new vs. history."""
    return current not in history
```

---

## TESTING CHECKLIST

After applying these changes:

- [ ] Backend starts: `cd backend && uvicorn main:app --reload`
- [ ] Test `/api/chat` with new services
- [ ] Test `/api/outbound/start` → starts call
- [ ] Test `/api/simulation/start` → sim session
- [ ] Test WebSocket connection via frontend
- [ ] Run frontend tests
- [ ] Check logger for service imports

---

## DEPLOYMENT CHECKLIST

- [ ] All new services imported successfully
- [ ] No circular import errors
- [ ] Requirements.txt has all dependencies
- [ ] Database seed completes: `python seed.py --verify`
- [ ] Test with 3-4 sample calls
- [ ] Check memory cleanup task runs
