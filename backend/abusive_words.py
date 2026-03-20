# Abusive word detection for multi-language support
# English, Tamil, and Tanglish (Tamil + English code-mix)

import re
from typing import List

ABUSIVE_WORDS_EN = {
    # Severe abusive language
    "fuck", "fucking", "shit", "shitty", "damn", "dammit", "asshole", "bastard",
    "bitch", "bitching", "dick", "dickhead", "jerk", "prick", "crap", "crappy",
    # Repeated intensifiers that signal extreme frustration
    "hate", "despise", "horrible", "terrible", "useless", "worthless", "stupid",
    "moron", "idiot", "retard", "idiot", "dumbass", "incompetent",
}

ABUSIVE_WORDS_TA = {
    # Tamil abusive words
    "పోయ్భ", "గా", "గూబ", "కుక్క", "సిగ్గు", "చిట్ట",  # Common Tamil abuse
    "తెవిచ", "చెవికి", "కండ", "గియ", "మల", "బొంగ", "బెన్నుగే",
    # More common Tamil abusive patterns
    "కుక్కకు", "నాయ్", "వివ", "ఛివ", "తుర్", "మోన్", "సోనియ", 
}

ABUSIVE_WORDS_TL = {
    # Tanglish (Tamil + English code-mix) abusive words
    "damn", "shit", "fuck", "bloody", "asshole",
    # Tanglish specific patterns (code-mixed)
    "da", "pa", "ma_iruku", "ombala", "moron_da", "idiot_da",
}

# Code-switching markers that might precede abusive language
CODE_SWITCH_MARKERS = {
    "da", "pa", "ma", "va", "le", "di",  # Tamil particles
    "so", "right", "no", "okay", "see",  # English discourse markers
}

def normalize_for_detection(text: str) -> str:
    """Normalize text for abusive word detection (lowercase, remove accents)"""
    return text.lower().strip()

def detect_abusive_language(transcript: str, language_mode: str = "auto") -> tuple[bool, set[str]]:
    """
    Detect abusive language in transcript.
    Returns: (is_abusive, matched_words_set)
    """
    normalized = normalize_for_detection(transcript)
    words = set(normalized.split())
    matched = set()
    
    # Check English
    for word in words:
        clean_word = re.sub(r'[^a-z0-9]', '', word)  # Remove punctuation
        if clean_word in ABUSIVE_WORDS_EN:
            matched.add(clean_word)
    
    # Check Tamil (if language mode includes Tamil)
    if language_mode in ["tamil", "auto", "tanglish"]:
        for word in words:
            if word in ABUSIVE_WORDS_TA:
                matched.add(word)
    
    # Check Tanglish
    if language_mode in ["tanglish", "auto"]:
        for word in words:
            if word in ABUSIVE_WORDS_TL:
                matched.add(word)
    
    return len(matched) > 0, matched

def extract_abusive_patterns(transcript: str) -> List[str]:
    """Extract sentences/phrases containing abusive language"""
    import re
    sentences = re.split(r'[.!?]', transcript)
    abusive_phrases = []
    
    for sentence in sentences:
        is_abusive, _ = detect_abusive_language(sentence)
        if is_abusive:
            abusive_phrases.append(sentence.strip())
    
    return abusive_phrases
