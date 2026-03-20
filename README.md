# Telecom AI Call System

A simulation-based AI call system with real-time speech recognition, text-to-speech, memory, decision-making, compliance checking, and post-call intelligence.

## Features

- **Simulated Incoming Calls**: Accept/reject incoming call simulation
- **Live Speech-to-Text**: Browser-based speech recognition (Web Speech API)
- **AI-Powered Responses**: Ollama-powered conversational AI
- **Text-to-Speech**: AI responses spoken aloud
- **Real-Time Intelligence**: Intent, sentiment, and urgency detection
- **Memory System**: Persistent customer history across calls
- **Post-Call Summary**: Automated AI-generated call summaries
- **Decision Engine**: Automatic escalation and resolution decisions
- **Compliance Checking**: Policy violation detection

## Architecture

```
Frontend (React + TypeScript)
├── Call UI with ring/accept/reject
├── Live transcript display
├── Speech recognition (mic input)
├── Text-to-speech (speaker output)
└── Real-time intelligence panel

Backend (FastAPI + Python)
├── Ollama integration (LLM)
├── SQLite database (memory)
├── Decision engine
└── REST API endpoints
```

## Prerequisites

1. **Python 3.9+** - Backend
2. **Node.js 18+** - Frontend
3. **Ollama** - Local LLM server

## Setup Instructions

### 1. Install and Start Ollama

```bash
# Download from https://ollama.ai
# After installation, pull the model:
ollama pull qwen3:4b
```

Make sure Ollama is running (it should start automatically).

### 2. Start the Backend

```bash
# Option 1: Use the batch script (Windows)
start-backend.bat

# Option 2: Manual setup
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Backend will be available at: `http://localhost:8000`

### 3. Start the Frontend

```bash
# Option 1: Use the batch script (Windows)
start-frontend.bat

# Option 2: Manual setup
cd frontend
npm install
npm run dev
```

Frontend will be available at: `http://localhost:5173`

## Usage

1. Open `http://localhost:5173` in Chrome (best speech support)
2. Select a customer from the left panel
3. Click "Simulate Incoming Call"
4. Accept the call
5. Click the microphone button to speak
6. Stop speaking to let the AI respond
7. End the call to see the AI-generated summary

## Database Schema

```
customers: id, name, phone, plan
calls: id, customer_id, start_time, end_time, status
conversations: id, call_id, speaker, message, timestamp, intent, sentiment
memory: id, customer_id, issue, status, sentiment, resolution
summaries: call_id, summary, issue, sentiment, resolved, action, compliance, decision
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /health | GET | System health check |
| /customers | GET | List all customers |
| /customers/{id}/memory | GET | Get customer history |
| /calls/start | POST | Start a new call |
| /calls/{id}/message | POST | Send message, get AI response |
| /calls/{id}/end | POST | End call, generate summary |
| /calls/{id}/transcript | GET | Get call transcript |
| /stats | GET | Get system statistics |

## Browser Support

- **Chrome**: Full support (recommended)
- **Edge**: Full support
- **Firefox**: Limited speech recognition
- **Safari**: Limited support

## Troubleshooting

### Ollama not connected
- Make sure Ollama is running: `ollama serve`
- Check if model is available: `ollama list`
- Pull model if missing: `ollama pull qwen3:4b`

### Speech recognition not working
- Use Chrome or Edge browser
- Allow microphone permission when prompted
- Make sure you're on localhost (HTTPS not required for localhost)

### AI responses slow
- Ollama first response may be slow (model loading)
- Subsequent responses should be faster
- Consider using a smaller model if hardware is limited

## Tech Stack

- **Frontend**: React 18, TypeScript, Vite, Web Speech API
- **Backend**: FastAPI, SQLAlchemy, SQLite, httpx
- **AI**: Ollama (qwen3:4b)
