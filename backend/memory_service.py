"""
Call memory and history management.
Tracks customer patterns, repeat issues, and conversation history.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from database import get_db, get_customer_by_id


class CallMemory:
    """In-memory store for current call context."""
    
    def __init__(self, session_id: str, customer_id: Optional[str] = None):
        self.session_id = session_id
        self.customer_id = customer_id
        self.conversation_history: List[Dict] = []
        self.sentiment_history: List[float] = []
        self.intent_history: List[str] = []
        self.language_history: List[str] = []
        self.escalation_triggered = False
        self.human_takeover_active = False
        self.created_at = datetime.utcnow()
        self.last_activity = datetime.utcnow()
    
    def add_turn(
        self,
        role: str,  # user, assistant, system
        content: str,
        sentiment: Optional[float] = None,
        intent: Optional[str] = None,
        language: Optional[str] = None,
        suggestions: Optional[List[Dict]] = None
    ) -> None:
        """Record a single turn in conversation."""
        turn = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
            "sentiment": sentiment,
            "intent": intent,
            "language": language,
            "suggestions": suggestions or []
        }
        self.conversation_history.append(turn)
        
        if sentiment is not None:
            self.sentiment_history.append(sentiment)
        if intent is not None:
            self.intent_history.append(intent)
        if language is not None:
            self.language_history.append(language)
        
        self.last_activity = datetime.utcnow()
    
    def get_last_n_turns(self, n: int = 5) -> List[Dict]:
        """Get last N turns from conversation."""
        return self.conversation_history[-n:] if self.conversation_history else []
    
    def get_sentiment_trend(self) -> str:
        """Get sentiment trend: improving, stable, worsening."""
        if len(self.sentiment_history) < 2:
            return "stable"
        
        recent = self.sentiment_history[-3:] if len(self.sentiment_history) >= 3 else self.sentiment_history
        trend = recent[-1] - recent[0]
        
        if trend < -0.2:
            return "worsening"
        if trend > 0.2:
            return "improving"
        return "stable"
    
    def get_repeat_intent_count(self, intent: str) -> int:
        """Count how many times same intent has appeared in history."""
        return self.intent_history.count(intent)
    
    def is_repeat_issue(self, intent: str, threshold: int = 2) -> bool:
        """Check if customer is repeating same issue."""
        return self.get_repeat_intent_count(intent) >= threshold
    
    def get_context_for_prompt(self) -> str:
        """Generate context string for RAG/Ollama prompt."""
        if not self.customer_id:
            return "No customer context available."
        
        context_parts = []
        
        # Recent conversation
        recent_turns = self.get_last_n_turns(4)
        if recent_turns:
            context_parts.append("Recent conversation:")
            for turn in recent_turns:
                prefix = "Customer:" if turn["role"] == "user" else "Agent:"
                context_parts.append(f"  {prefix} {turn['content'][:60]}...")
        
        # Sentiment trend
        trend = self.get_sentiment_trend()
        context_parts.append(f"\nSentiment trend: {trend}")
        
        # Intent pattern
        if self.intent_history:
            most_common_intent = max(set(self.intent_history), key=self.intent_history.count)
            repeat_count = self.get_repeat_intent_count(most_common_intent)
            context_parts.append(f"Primary issue: {most_common_intent} (mentioned {repeat_count} times)")
        
        # Language
        if self.language_history:
            context_parts.append(f"Customer language: {self.language_history[-1]}")
        
        return "\n".join(context_parts)


class CustomerPattern:
    """Track patterns for a specific customer across calls."""
    
    def __init__(self, customer_id: str):
        self.customer_id = customer_id
        self.first_contact = None
        self.last_contact = None
        self.total_calls = 0
        self.resolved_calls = 0
        self.repeat_intents: Dict[str, int] = {}  # intent -> count
        self.average_sentiment = 0.0
        self.escalation_count = 0
        self.churn_risk_detected = False
    
    def add_call(
        self,
        resolved: bool,
        intents: List[str],
        sentiment_avg: float,
        escalated: bool = False
    ) -> None:
        """Record completion of a call."""
        now = datetime.utcnow()
        
        if self.first_contact is None:
            self.first_contact = now
        
        self.last_contact = now
        self.total_calls += 1
        
        if resolved:
            self.resolved_calls += 1
        
        # Track repeated intents
        for intent in intents:
            self.repeat_intents[intent] = self.repeat_intents.get(intent, 0) + 1
        
        # Rolling average sentiment
        self.average_sentiment = (
            (self.average_sentiment * (self.total_calls - 1) + sentiment_avg) / self.total_calls
        )
        
        if escalated:
            self.escalation_count += 1
        
        # Check churn risk
        if self.total_calls >= 3 and self.resolved_calls == 0:
            self.churn_risk_detected = True
    
    def get_repeat_issue(self) -> Optional[str]:
        """Get the most repeated issue for this customer."""
        if not self.repeat_intents:
            return None
        
        intent, count = max(self.repeat_intents.items(), key=lambda x: x[1])
        
        # Only return if repeated 2+ times
        if count >= 2:
            return intent
        
        return None
    
    def get_risk_score(self) -> float:
        """
        Calculate churn risk score 0.0-1.0.
        Higher = more likely to churn.
        """
        score = 0.0
        
        # Unresolved calls → high churn risk
        if self.total_calls > 0:
            resolution_rate = self.resolved_calls / self.total_calls
            score += (1 - resolution_rate) * 0.4
        
        # Multiple escalations → risk
        if self.escalation_count >= 2:
            score += 0.3
        
        # Repeat unresolved issues → risk
        if self.churn_risk_detected:
            score += 0.2
        
        # Recent negative sentiment → risk
        if self.average_sentiment < -0.5:
            score += 0.1
        
        return min(1.0, score)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API."""
        return {
            "customer_id": self.customer_id,
            "total_calls": self.total_calls,
            "resolved_calls": self.resolved_calls,
            "repeat_issue": self.get_repeat_issue(),
            "risk_score": self.get_risk_score(),
            "escalation_count": self.escalation_count,
            "average_sentiment": round(self.average_sentiment, 2),
            "first_contact": self.first_contact.isoformat() if self.first_contact else None,
            "last_contact": self.last_contact.isoformat() if self.last_contact else None
        }


# Session-level call memories
_active_memories: Dict[str, CallMemory] = {}

# Customer-level pattern tracking
_customer_patterns: Dict[str, CustomerPattern] = {}


def get_or_create_memory(session_id: str, customer_id: Optional[str] = None) -> CallMemory:
    """Get or create call memory for session."""
    if session_id not in _active_memories:
        _active_memories[session_id] = CallMemory(session_id, customer_id)
    return _active_memories[session_id]


def end_call_memory(session_id: str) -> Optional[CallMemory]:
    """End session and retrieve memory."""
    memory = _active_memories.get(session_id)
    if memory:
        # Update customer pattern if applicable
        if memory.customer_id:
            if memory.customer_id not in _customer_patterns:
                _customer_patterns[memory.customer_id] = CustomerPattern(memory.customer_id)
            
            pattern = _customer_patterns[memory.customer_id]
            avg_sentiment = (
                sum(memory.sentiment_history) / len(memory.sentiment_history)
                if memory.sentiment_history else 0.0
            )
            pattern.add_call(
                resolved=not memory.escalation_triggered,
                intents=memory.intent_history,
                sentiment_avg=avg_sentiment,
                escalated=memory.escalation_triggered
            )
        
        del _active_memories[session_id]
    
    return memory


def get_customer_pattern(customer_id: str) -> Optional[Dict]:
    """Get tracked pattern for customer."""
    if customer_id in _customer_patterns:
        return _customer_patterns[customer_id].to_dict()
    return None


def get_customer_summary(customer_id: str) -> Dict:
    """
    Get comprehensive customer summary for greeting/context.
    Combines DB data with runtime patterns.
    """
    from database import get_customer_by_id
    
    db_customer = get_customer_by_id(customer_id)
    pattern = get_customer_pattern(customer_id)
    
    summary = {
        "customer_id": customer_id,
        "name": db_customer.get("full_name") if db_customer else "Customer",
        "plan": db_customer.get("plan_name") if db_customer else "Unknown",
        "total_calls": pattern.get("total_calls", 0) if pattern else 0,
        "repeat_issue": pattern.get("repeat_issue") if pattern else None,
        "risk_score": pattern.get("risk_score", 0) if pattern else 0,
        "last_contact": pattern.get("last_contact") if pattern else None,
    }
    
    return summary


def cleanup_old_memories(max_age_hours: int = 24):
    """Clean up memories older than max_age."""
    threshold = datetime.utcnow() - timedelta(hours=max_age_hours)
    
    to_delete = []
    for session_id, memory in _active_memories.items():
        if memory.last_activity < threshold:
            to_delete.append(session_id)
    
    for session_id in to_delete:
        end_call_memory(session_id)
