"""
Enhanced sentiment detection with multi-language support.
No AI API calls - all local rule-based detection.
"""

from typing import Literal, Union, Optional, cast
from dataclasses import dataclass

SentimentLabel = Literal["angry", "frustrated", "mildly_frustrated", "neutral", "satisfied", "positive"]

SENTIMENT_WEIGHTS = {
    "angry": {
        "en": [
            "terrible", "useless", "furious", "disgusting", "unacceptable",
            "awful", "worst", "ridiculous", "incompetent", "pathetic",
            "outrageous", "disgraceful", "appalling", "shocking", "disgusted"
        ],
        "ta": ["மோசமான", "பயனற்ற", "கோபமாக", "அருவருப்பான", "ஏற்றமில்லாத"],
        "tanglish": ["worst service", "useless la", "terrible da", "disgrace panni"]
    },
    "frustrated": {
        "en": [
            "frustrated", "annoyed", "unhappy", "disappointed", "again",
            "still not", "never fixed", "third time", "keeps happening",
            "not resolved", "taking too long", "waiting forever", "ridiculous wait",
            "fed up", "sick of", "can't believe"
        ],
        "ta": ["கோபப்படுகிறேன்", "சரிசெய்யவில்லை", "மீண்டும்", "சிரமம்"],
        "tanglish": ["still fix pannala", "again problem", "time waste panni", "frustrating da"]
    },
    "mildly_frustrated": {
        "en": [
            "a bit annoyed", "not happy", "concerned", "worried",
            "not working properly", "issue", "problem", "trouble",
            "disappointed", "slight concern", "seems off", "not quite right"
        ],
        "ta": ["கவலைப்படுகிறேன்", "சரியில்லை", "சிக்கல்"],
        "tanglish": ["bit frustrating", "sari illa", "problem iruku"]
    },
    "churn_risk": {
        "en": [
            "cancel", "leave", "switch", "bt ", "vodafone", "ee ", "three ",
            "quit", "terminate", "closing account", "pac code", "port my number",
            "going elsewhere", "better deal", "competitor", "taking my business"
        ],
        "ta": ["ரத்து செய்", "வேற நிறுவனம்", "நிறுத்துகிறேன்"],
        "tanglish": ["cancel pannuven", "vera company poven", "bt poren"]
    },
    "satisfied": {
        "en": [
            "thank", "great", "appreciate", "happy", "excellent",
            "perfect", "wonderful", "brilliant", "fantastic", "solved",
            "resolved", "fixed", "working now", "thank you so much"
        ],
        "ta": ["நன்றி", "சரியாக", "மகிழ்ச்சி"],
        "tanglish": ["thanks da", "super la", "solved achu"]
    },
    "positive": {
        "en": ["yes", "sure", "okay", "go ahead", "sounds good", "agreed", "please", "alright"],
        "ta": ["சரி", "ஆம்"],
        "tanglish": ["okay da", "sari", "proceed panu"]
    }
}


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""
    label: SentimentLabel
    score: float  # -1.0 to 1.0
    trajectory: Literal["worsening", "stable", "improving"]
    trigger_phrase: Optional[str]
    churn_risk: bool
    escalation_needed: bool


def detect_sentiment(text: str, language: str = "en") -> SentimentResult:
    """
    Detect sentiment from customer text.
    
    Returns: SentimentResult with label, score, trajectory, trigger phrase, flags
    """
    if not text:
        return SentimentResult(
            label="neutral",
            score=0.0,
            trajectory="stable",
            trigger_phrase=None,
            churn_risk=False,
            escalation_needed=False
        )
    
    text_lower = text.lower()
    matched_category = "neutral"
    matched_phrase = None
    is_churn = False
    
    # Check in priority order: angry > churn_risk > frustrated > ...
    priority_order = ["angry", "churn_risk", "frustrated", "mildly_frustrated", "satisfied", "positive"]
    
    for category in priority_order:
        weight_list = SENTIMENT_WEIGHTS.get(category, {})
        for lang_key in ["en", "ta", "tanglish"]:
            phrases = weight_list.get(lang_key, [])
            for phrase in phrases:
                if phrase.lower() in text_lower:
                    matched_category = category
                    matched_phrase = phrase
                    if category == "churn_risk":
                        is_churn = True
                    break
            if matched_phrase:
                break
        if matched_phrase:
            break
    
    # Score mapping
    score_map = {
        "angry": -0.90,
        "churn_risk": -0.75,
        "frustrated": -0.55,
        "mildly_frustrated": -0.28,
        "neutral": 0.0,
        "positive": 0.35,
        "satisfied": 0.80
    }
    
    base_score = score_map.get(matched_category, 0.0)
    
    # Add micro-variation based on text to ensure score changes per turn
    variation = (len(text) % 7 - 3) * 0.02
    final_score = max(-1.0, min(1.0, base_score + variation))
    final_score = round(final_score, 3)
    
    # Urgency word boosts
    urgency_words = ["immediately", "urgent", "now", "today", "asap", "right now", "emergency"]
    if any(w in text_lower for w in urgency_words):
        final_score = max(-1.0, final_score - 0.15)
    
    # Determine if escalation needed
    label: SentimentLabel = cast(SentimentLabel, matched_category if matched_category != "churn_risk" else "frustrated")
    escalation_needed = label == "angry" or is_churn or final_score < -0.6
    
    return SentimentResult(
        label=label,
        score=final_score,
        trajectory="stable",  # will be updated by caller
        trigger_phrase=matched_phrase,
        churn_risk=is_churn,
        escalation_needed=escalation_needed
    )


def get_sentiment_arc(sentiment_history: list[SentimentResult]) -> str:
    """
    Get trajectory from sentiment history.
    Returns: 'worsening', 'stable', or 'improving'
    """
    if len(sentiment_history) < 2:
        return "stable"
    
    recent = sentiment_history[-3:] if len(sentiment_history) >= 3 else sentiment_history
    if len(recent) < 2:
        return "stable"
    
    trend = recent[-1].score - recent[0].score
    if trend < -0.2:
        return "worsening"
    if trend > 0.2:
        return "improving"
    return "stable"


def should_escalate(sentiment_history: list[SentimentResult]) -> bool:
    """
    Escalate if score drops below -0.5 for 2+ consecutive turns.
    """
    if len(sentiment_history) < 2:
        return False
    
    recent = sentiment_history[-2:]
    return all(s.score < -0.5 for s in recent)


def get_de_escalation_suggestion(
    sentiment: SentimentResult,
    customer_name: str,
    language: str = "en"
) -> str:
    """Return a de-escalation script based on sentiment and language."""
    
    scripts = {
        "en": {
            "angry": f"I completely understand your frustration {customer_name}, and I sincerely apologise. This is absolutely not the standard we hold ourselves to, and I'm going to make sure this is resolved right now.",
            "frustrated": f"I hear you {customer_name}, and I'm really sorry this has been so difficult. Let me take full ownership of this and get it sorted for you today.",
            "churn_risk": f"I completely understand {customer_name}, and I don't want to lose you. Before you make any decisions, can I offer you something to make this right?"
        },
        "ta": {
            "angry": f"{customer_name}, உங்கள் கோபம் புரிகிறது. நான் மன்னிப்பு கேட்கிறேன். இதை இப்போதே சரிசெய்கிறேன்.",
            "frustrated": f"{customer_name}, உங்கள் பிரச்சனையை நான் புரிந்துகொள்கிறேன். இதை தீர்க்கிறேன்.",
            "churn_risk": f"{customer_name}, நீங்கள் போவதை நான் விரும்பவில்லை. ஒரு சிறப்பு சலுகை தருகிறேன்."
        },
        "tanglish": {
            "angry": f"{customer_name}, ungal frustration puriyuthu. Sorry da. Ipave fix pannurom.",
            "frustrated": f"I understand {customer_name}. Ungal problem-a serious-a eduthukuren. Today fix pannuven.",
            "churn_risk": f"{customer_name}, please don't leave. Special offer tharuven ungalukku."
        }
    }
    
    lang_scripts = scripts.get(language, scripts["en"])
    sentiment_key = sentiment.label if not sentiment.churn_risk else "churn_risk"
    
    return lang_scripts.get(sentiment_key, lang_scripts.get("frustrated", ""))


def urgency_level(sentiment: SentimentResult) -> Literal["low", "medium", "high"]:
    """
    Map sentiment to urgency level for agent display.
    """
    if sentiment.label == "angry" or sentiment.churn_risk:
        return "high"
    if sentiment.label in ["frustrated", "mildly_frustrated"]:
        return "medium"
    return "low"
