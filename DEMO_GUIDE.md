# 🎬 INFYND AIM 2026 - COMPLETE DEMO SCRIPT
## AI with Memory for Telecom Call Centers

### System Architecture Overview
```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React + TypeScript)                │
│  • Real-time Intelligence Panel                              │
│  • Human Takeover Mode (Agent Text → TTS)                   │
│  • Call Outcome Feedback                                     │
│  • Abusive Language Warnings                                 │
│  • Repeat Caller Alerts                                      │
└────────────────────┬────────────────────────────────────────┘
                     │ WebSocket + HTTP
┌────────────────────┴────────────────────────────────────────┐
│              Backend (FastAPI + Python)                       │
│  ✓ Abusive word detection (EN/TA/TL)                        │
│  ✓ Repeat issue pattern detection                           │
│  ✓ Real-time sentiment + escalation logic                   │
│  ✓ Human takeover mode API                                  │
│  ✓ Call outcome learning                                    │
│  ✓ Escalation to human phone number                         │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────────┐
│                  SQLite Database                              │
│  • Customers + repeat issue history                          │
│  • Call outcomes (resolved vs repeat)                        │
│  • Escalation logs                                           │
│  • Human takeover transcripts                                │
│  • Assist events with sentiment arc                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 STARTUP INSTRUCTIONS

### Step 1: Kill Any Existing Processes
```bash
cd C:\Users\navee\Desktop\Mic
# Kill old Python/Node/Ollama processes if running
netstat -ano | findstr ":8020 :5173 :11434"
```

### Step 2: Start the Full Stack
```bash
# From project root, run this script (opens 2 windows)
.\start-all.bat

# OR start individually:
# Terminal 1 - Backend (port 8020)
.\start-backend.bat

# Terminal 2 - Frontend (port 5173)
.\start-frontend.bat
```

### Step 3: Verify Services
```bash
# Backend health check
http://localhost:8020/health
# Expected response: {"status":"healthy","ollama":"connected"}

# Frontend should open at:
http://localhost:5173
```

---

## 📋 DEMO SCENARIOS

### SCENARIO 1: Repeat Caller with Escalation
**Goal:** Show pattern detection + 2-turn angry escalation + human takeover option

#### Setup
- Start a new inbound call
- Customer phone: "+1234567890" (matches sample customer "James Richardson")

#### Execution
1. **Turn 1 - Neutral to Frustrated**
   ```
   Customer: "Hey, I've got terrible signal again. This is the 4th time!"
   ```
   - System detects: intent="network_outage", sentiment="frustrated", repeat_issue_count=4
   - IntelligencePanel shows: 🔄 **Repeat Caller Pattern Detected** (4+ calls)
   - Suggestion shows: "Previous attempts may not have fully resolved the root cause"
   - NO escalation alert yet (frustration, not angry)

2. **Turn 2 - Escalation Trigger**
   ```
   Customer: "This is completely unacceptable! Your service is terrible! I'm sick of this!"
   ```
   - System detects: sentiment="angry", angry_turns=2, escalation_alert=TRUE
   - IntelligencePanel shows: 🚨 **Escalation Alert** + RED buttons
   - Shows: 2 buttons: "📞 Escalate to Human" | "👤 Human Takeover"

3. **Click "👤 Human Takeover"**
   - HumanTakeoverPanel appears with:
     - Text input box for agent to type
     - 3 AI suggestions (empathetic, understanding, professional tones)
     - Send button converts to TTS
   - Panel shows: "🤖 → 👤 Human Takeover Mode Active"

4. **Agent Takes Over**
   - Agent types: "I completely understand. Let me escalate to our technical team immediately."
   - Click "📢 Send Text (→ TTS)"
   - Text converts to speech and plays to customer
   - Message logged: "✓ I completely understand. Let me escalate..."

5. **Return to AI Mode (Optional)**
   - Click "✓ Return to AI-Assisted Mode"
   - System resumes AI- assisted handling

**Key Features Demonstrated:**
✅ Repeat caller pattern detection (4 calls same issue)
✅ 2-turn angry escalation (turn 1: alert=false, turn 2: alert=true)
✅ Sentiment arc visualization ("frustrated → angry")
✅ Human takeover with agent text input + TTS
✅ AI suggestions alongside human input

---

### SCENARIO 2: Abusive Language Detection
**Goal:** Show immediate escalation when abusive language detected

#### Setup
- Start new inbound call
- Customer phone: "+0987654321" (matches "Jane Smith")

#### Execution
1. **Initial Complaint (Neutral)**
   ```
   Customer: "My bill is wrong, I was overcharged $50."
   ```
   - System detects: intent="billing_dispute", sentiment="neutral"
   - IntelligencePanel normal (no alerts)

2. **Abusive Language Turn**
   ```
   Customer: "You're useless! This damn service is fucking terrible!"
   ```
   - System detects: abusive_language_detected=TRUE
   - Flagged words: "useless", "damn", "fucking", "terrible"
   - IntelligencePanel shows: **⚠️ ABUSIVE LANGUAGE DETECTED**
   - Red box with: "Flagged: useless, damn, fucking, terrible"
   - Message: "Immediate escalation required. Transfer to senior agent."
   - Big RED button: "🚨 Escalate Immediately"

3. **Click Escalation Button**
   - System calls `/api/escalate` with reason="abusive_language"
   - Shows popup: `"Escalating to: 1-800-TELECORP"` (escalation phone)
   - Reference ID provided for call tracking

**Key Features Demonstrated:**
✅ Multi-language abusive word detection (EN/TA/TL)
✅ Immediate escalation on abusive language
✅ List of flagged words shown
✅ Escalation phone number transmitted
✅ Call reference ID for agent handoff

---

### SCENARIO 3: Multilingual Code-Switching
**Goal:** Show language detection + adaptation for Tanglish/Tamil customers

#### Setup
- Start new inbound call
- New customer (unknown phone number)

#### Execution
1. **English Turn**
   ```
   Customer: "Hi, I need help with my plan options."
   ```
   - System detects: language_mode="english", intent="plan_upgrade"
   - Suggestions in English tone

2. **Code-Switch to Tanglish/Tamil**
   ```
   Customer: "Enna signal problem romba bad ah iruku. Nee service kamap poga da!"
   ```
   - System detects: language_mode="tanglish"
   - Sentiment: "frustrated"
   - Suggestions adapt: "Tanglish/Tamil tone with English slang"

3. **Back to English**
   ```
   Customer: "Can you please fix the network issue?"
   ```
   - System detects: switched back to language_mode="english"

**Key Features Demonstrated:**
✅ Real-time language mode detection (English/Tamil/Tanglish)
✅ Code-switching mid-call handled
✅ Suggestions adapt to language (tone_match shows adaptation)
✅ Sentiment Arc shows sentiment transitions across languages

---

### SCENARIO 4: Call Outcome Learning
**Goal:** Show feedback loop for improving suggestions over time

#### Setup
- Complete any call scenario above

#### Execution
1. **End Call**
   - Click "End Call" button
   - System saves call session

2. **Feedback Modal (Optional)**
   - System could ask: "Was this issue resolved?"
   - Agent selects: Yes ✓ | No ✗ | Escalated 📞
   - Optional feedback: "Did suggestion #2 help?"

3. **Learning Storage**
   - POST to `/api/call-outcome` with:
     ```json
     {
       "session_id": "rt-xyz",
       "resolved": true,
       "resolution_type": "technical_fix",
       "feedback_text": "Customer satisfied with network troubleshooting"
     }
     ```

4. **System Learns**
   - Next time similar issue detected:
     - Same suggestion will have higher resolution_likelihood
     - Ranked higher in suggestions list
     - Agent sees: "Suggestion #1: Likelihood 95% (previously resolved)"

**Key Features Demonstrated:**
✅ Call outcome tracking (resolved/repeat)
✅ Feedback loop integration
✅ Learning signals propagated to ranking
✅ Historical patterns used for future suggestions

---

## 📊 LIVE TRANSCRIPT DEMO

### Real-Time Display Features

During an active call, IntelligencePanel shows:

```
┌─ CURRENT INTENT ─────────────────────────┐
│ network_outage                            │
└───────────────────────────────────────────┘

┌─ SENTIMENT ─────┬─ URGENCY ────────────┐
│ angry ❌        │ high ❌              │
└─────────────────┴──────────────────────┘

┌─ SENTIMENT STATE ───────────────────────┐
│ angry_or_churn_risk                     │
└───────────────────────────────────────────┘

┌─ SENTIMENT ARC ──────────────────────────┐
│ frustrated → frustrated → angry          │
└───────────────────────────────────────────┘

┌─ LANGUAGE MODE ────────────────────────┐
│ tanglish                               │
└────────────────────────────────────────┘

┌─ 🚨 ESCALATION ALERT ──────────────────┐
│ Customer emotion is deteriorating.      │
│                                        │
│ [📞 Escalate] [👤 Takeover]           │
└────────────────────────────────────────┘

┌─ 🔄 REPEAT CALLER PATTERN ─────────────┐
│ Called 4+ times about this issue        │
│ Previous attempts didn't resolve        │
│                                        │
│ [💡 Take Over (Investigate Root Cause)]│
└────────────────────────────────────────┘

┌─ TRIGGER PHRASES ──────────────────────┐
│ terrible, urgent, network, outage      │
└────────────────────────────────────────┘

┌─ RANKED AGENT ASSIST ──────────────────┐
│ Option 1 • Likelihood 92% • Tone:      │
│ Empathetic                             │
│ "I understand how frustrating this is. │
│  Let me get our tech team on this."    │
│                                        │
│ Option 2 • Likelihood 84% • Tone:      │
│ Professional                           │
│ "Let me run a diagnostic on your line  │
│  right now while we talk..."           │
│                                        │
│ Option 3 • Likelihood 71% • Tone:      │
│ Offering                               │
│ "For this disruption, I'd like to      │
│  offer you 2 months of service credit.│
└────────────────────────────────────────┘

┌─ 👤 HUMAN TAKEOVER MODE ───────────────┐
│ Agent Input:                           │
│ ┌──────────────────────────────────┐  │
│ │ What would you like to say?      │  │
│ │ [text area for agent input]      │  │
│ │ [📢 Send Text (→ TTS)]           │  │
│ └──────────────────────────────────┘  │
│                                        │
│ 💡 AI Suggestions:                     │
│ • Empathetic: "I completely understand"│
│ • Understanding: "Let's resolve this"  │
│ • Professional: "I'll escalate..."     │
└────────────────────────────────────────┘
```

---

## 🧪 API TEST CASES

### Test 1: Abusive Language Detection
```bash
curl -X POST http://localhost:8020/api/realtime/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-abuse",
    "chunk": "This fucking service is shit! You guys are useless!",
    "role": "customer",
    "call_type": "inbound",
    "customer_phone": "+1234567890"
  }'
```
**Expected Response:**
```json
{
  "escalation_alert": true,
  "abusive_language_detected": true,
  "abusive_words": ["fucking", "shit", "useless"],
  "suggestions": [...]
}
```

### Test 2: Repeat Caller Detection (3+ times)
```bash
curl -X GET http://localhost:8020/api/repeat-caller-info/%2B1234567890
```
**Expected Response:**
```json
{
  "is_repeat_caller": true,
  "issue_count": 4,
  "prev_issues": ["network_outage", "billing_dispute"],
  "recommendation": "Flag for escalation. Pattern detected: customer called 3+ times.",
  "recent_calls": [...]
}
```

### Test 3: Human Takeover Enable
```bash
curl -X POST http://localhost:8020/api/human-takeover/enable \
  -H "Content-Type: application/json" \
  -d '{"session_id": "test-takeover"}'
```
**Expected Response:**
```json
{
  "success": true,
  "mode": "human_takeover_enabled",
  "message": "Human takeover enabled. AI will provide suggestions only."
}
```

### Test 4: Send Human Text → TTS
```bash
curl -X POST http://localhost:8020/api/human-takeover/send-text \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-takeover",
    "text": "I understand your frustration. Let me escalate this to headquarters."
  }'
```
**Expected Response:**
```json
{
  "success": true,
  "text_sent": "I understand your frustration...",
  "audio_url": "/api/tts?text=I%20understand...",
  "ai_suggestions": [...]
}
```

### Test 5: Save Call Outcome
```bash
curl -X POST http://localhost:8020/api/call-outcome \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-takeover",
    "resolved": true,
    "resolution_type": "technical_fix",
    "feedback_text": "Network issue resolved after tech team intervention"
  }'
```
**Expected Response:**
```json
{
  "success": true,
  "message": "Call outcome recorded. AI learning updated.",
  "learning_stored": true
}
```

### Test 6: Manual Escalation
```bash
curl -X POST http://localhost:8020/api/escalate \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "test-escalate",
    "reason": "customer_request",
    "escalation_phone": "1-800-TELECORP"
  }'
```
**Expected Response:**
```json
{
  "success": true,
  "escalation_phone": "1-800-TELECORP",
  "reference_id": "test-escalate",
  "wait_time_estimate": "2-3 minutes"
}
```

---

## 📱 UI WALKTHROUGH FOR JUDGES

### Step 1: Shows Real-Time Sentiment Arc
"Notice the SentimentArc visualization - it tracks every emotion shift. When a customer goes from frustrated to angry, we see it instantly: *frustrated → angry*. This triggers escalation logic."

### Step 2: Demonstrates Repeat Caller Alert
"If this same customer calls again about the same issue, the system flags it. After 3 calls, we proactively suggest human investigation. Why? Because previous fixes didn't stick."

### Step 3: Abusive Language Handling
"If a customer uses abusive language in any of our supported languages (English/Tamil/Tanglish), the system flags it immediately and offers instant escalation. No delay."

### Step 4: Shows Human Takeover in Action
"When an agent takes over, they type naturally. The system converts their exact text to speech. But they also get AI suggestions in case they need ideas."

### Step 5: Closing Statement
"All of this - sentiment, intentions, language modes, patterns - is learned and stored. Next time a similar call comes in, the system is smarter. It suggests interventions that previously resolved similar issues."

---

## 🎯 KEY METRICS FOR JUDGES

| Feature | Impact | Status |
|---------|--------|--------|
| **Repeat Caller Detection** | Identifies stuck issues (3+ calls), prevents repeat escalations | ✅ Coded |
| **Abusive Word Detection** | Multi-language (EN/TA/TL), immediate escalation | ✅ Coded |
| **2-Turn Escalation Logic** | Avoids false alarms, escalates only sustained anger | ✅ Coded |
| **Human Takeover Mode** | Agent types → TTS, keeps AI suggestions in sidebar | ✅ Coded |
| **Sentiment Arc Tracking** | Full call emotion journey visible in UI | ✅ Coded |
| **Language-Aware Responses** | Adapts suggestions based on English/Tamil/Tanglish | ✅ Coded |
| **Call Outcome Learning** | Records what resolved, improves future suggestions | ✅ Coded |
| **WebSocket Streaming** | Real-time updates to UI as call progresses | ✅ Coded |

---

## ⚠️ KNOWN LIMITATIONS & NOTES

1. **Tamil Generation**: Currently using heuristic-based Tamil text + Tanglish adaptation (not full LLM generation)
2. **TTS Voices**: Using browser default voices (English primary, may not have perfect Tamil/Tanglish)
3. **Abusive Words**: Limited to curated lists; can be extended
4. **Escalation Phone**: Currently hardcoded to "1-800-TELECORP" (can be customized per customer/region)
5. **Learning Feedback**: Manual feedback required (can be made automatic via call outcome prediction)

---

## 🔧 TROUBLESHOOTING

| Issue | Solution |
|-------|----------|
| Backend won't start | Ensure ports 8020, 11434 are free |
| Frontend WebSocket fails | Check browser console; verify ws://localhost:8020 accessible |
| Ollama not found | Run `ollama serve` separately; backend will auto-connect |
| No TTS output | Verify browser has speaker permission; check Volume |
| Escalation button inactive | Ensure escalationAlert=true or abusiveLanguageDetected=true |

---

## 📞 DEMO PHONE NUMBERS (Pre-loaded Customers)

Use these to trigger different scenarios:

- **+1234567890** → "James Richardson" (Premium, repeat issues) → Triggers repeat pattern
- **+0987654321** → "Jane Smith" (Basic) → Good for new scenario
- **+1122334455** → "Bob Wilson" (Business) → Enterprise scenario
- **Unknown number** → Triggers new caller flow (collect basics first)

---

## 🏆 INFYND AIM 2026 CHECKLIST

- ✅ Call ingestion (WebSocket streaming)
- ✅ Intent detection (continuous, multi-turn)
- ✅ Call type awareness (inbound vs outbound branches)
- ✅ Noisy transcript handling
- ✅ Real-time sentiment detection + trajectory tracking
- ✅ Agent assist (2-3 ranked options per turn)
- ✅ Sentiment arc state tracking (visualized)
- ✅ Multilingual handling (English/Tamil/Tanglish)
- ✅ Escalation alerts (2-turn angry threshold)
- ✅ Problem-first ordering (upsell in rank 3 only)
- ✅ Persistence (DB logging of all assist events)
- ✅ **BONUS: Abusive word detection & escalation**
- ✅ **BONUS: Repeat caller pattern memory**
- ✅ **BONUS: Human takeover with TTS**
- ✅ **BONUS: Call outcome learning**

---

**Ready to demo! Start with `.\start-all.bat` and navigate to http://localhost:5173**
