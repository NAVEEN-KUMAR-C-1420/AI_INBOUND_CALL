"""
Multi-language detection and response routing.
Supports English, Tamil (தமிழ்), and Tanglish (code-mixed).
"""

import re
from typing import Literal, Optional
from langdetect import detect, LangDetectException

TAMIL_UNICODE_RANGE = r'[\u0B80-\u0BFF]'

Language = Literal["en", "ta", "tanglish", "unknown"]


def detect_language(text: str) -> Language:
    """
    Detect language from text.
    Returns: 'English', 'Tamil', 'tanglish', or 'unknown'
    """
    if not text:
        return "en"
    
    has_tamil = has_tamil_chars(text)
    has_latin = has_latin_chars(text)
    
    # If both Tamil and Latin characters → Tanglish (code-mixed)
    if has_tamil and has_latin:
        return "tanglish"
    
    # If only Tamil characters → Tamil
    if has_tamil:
        return "ta"
    
    # Try langdetect library
    try:
        result: Optional[str] = detect(text)
        if result == "ta":
            return "ta"
        if result == "en":
            return "en"
    except (LangDetectException, Exception):
        pass
    
    # Default to English if unsure
    return "en"


def has_tamil_chars(text: str) -> bool:
    """Check if text contains Tamil Unicode characters."""
    return bool(re.search(TAMIL_UNICODE_RANGE, text or ""))


def has_latin_chars(text: str) -> bool:
    """Check if text contains Latin/English characters."""
    return bool(re.search(r'[a-zA-Z]', text or ""))


def get_response_language(
    customer_language: Language,
    session_language_history: list
) -> Language:
    """
    Decide what language the AI should respond in.
    
    Rules:
    - If customer just spoke Tamil → respond in Tamil
    - If customer is Tanglish → respond in Tanglish
    - If customer switched from Tamil to English → follow switch, respond English
    - If customer switched from English to Tamil → follow switch, respond Tamil
    - Default: English
    """
    if not session_language_history:
        return customer_language or "en"
    
    last_lang = session_language_history[-1] if session_language_history else "en"
    
    # If customer stays with same language → use it
    if customer_language == last_lang:
        return customer_language
    
    # If customer switches TO English from Tamil → follow switch
    if customer_language == "en" and last_lang in ["ta", "tanglish"]:
        return "en"
    
    # If customer switches TO Tamil/Tanglish → follow switch
    if customer_language in ["ta", "tanglish"]:
        return customer_language
    
    return "en"


def get_system_prompt_language_instruction(language: Language) -> str:
    """Return language instruction to inject into system prompt."""
    instructions = {
        "en": "Respond in English only.",
        "ta": "Respond in Tamil (தமிழ்) only. Use formal Tamil. Example: நன்றி, உங்கள் சிக்கலை நான் தீர்க்கிறேன்.",
        "tanglish": "Respond in Tanglish (Tamil + English mixed). Example: Ungal account-a check pannurom, kondiya neram aagum.",
        "unknown": "Respond in English only."
    }
    return instructions.get(language, instructions["en"])


def translate_intent_keywords_check(
    text: str,
    intent_keywords: list,
    tamil_keywords: Optional[list] = None,
    tanglish_keywords: Optional[list] = None
) -> bool:
    """
    Check if text matches intent keywords across all three language lists.
    """
    text_lower = text.lower()
    all_keywords = intent_keywords + (tamil_keywords or []) + (tanglish_keywords or [])
    return any(kw.lower() in text_lower for kw in all_keywords)


def get_stty_locale_for_language(language: Language) -> str:
    """Get locale string for speech-to-text language setting."""
    locale_map = {
        "en": "en-GB",
        "ta": "ta-IN",
        "tanglish": "en-IN",  # Indian English recognizes code-mixed speech best
        "unknown": "en-GB"
    }
    return locale_map.get(language, "en-GB")


def get_tts_voice_hint(language: Language) -> str:
    """Get voice preference hint for text-to-speech."""
    voice_map = {
        "en": "English GB female",
        "ta": "Tamil (India)",
        "tanglish": "English India female",
        "unknown": "English GB female"
    }
    return voice_map.get(language, "English GB female")
