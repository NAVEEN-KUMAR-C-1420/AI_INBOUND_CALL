#!/usr/bin/env python
"""
Comprehensive Test Suite for Telecom AI Call Center
Tests all services, API endpoints, and core functionality
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

print("=" * 80)
print("🧪 TELECOM AI CALL CENTER - COMPREHENSIVE TEST SUITE")
print("=" * 80)

# ============================================================================
# TEST 1: IMPORT VALIDATION
# ============================================================================
print("\n📦 TEST 1: VERIFYING ALL IMPORTS")
print("-" * 80)

test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "details": []
}

try:
    from language_service import detect_language, get_response_language
    test_results["passed"] += 1
    test_results["details"].append("✅ language_service imported")
except Exception as e:
    test_results["failed"] += 1
    test_results["details"].append(f"❌ language_service: {str(e)}")
test_results["total"] += 1

try:
    from sentiment_service import detect_sentiment
    test_results["passed"] += 1
    test_results["details"].append("✅ sentiment_service imported")
except Exception as e:
    test_results["failed"] += 1
    test_results["details"].append(f"❌ sentiment_service: {str(e)}")
test_results["total"] += 1

try:
    from memory_service import get_or_create_memory
    test_results["passed"] += 1
    test_results["details"].append("✅ memory_service imported")
except Exception as e:
    test_results["failed"] += 1
    test_results["details"].append(f"❌ memory_service: {str(e)}")
test_results["total"] += 1

try:
    from outbound_service import start_outbound_call
    test_results["passed"] += 1
    test_results["details"].append("✅ outbound_service imported")
except Exception as e:
    test_results["failed"] += 1
    test_results["details"].append(f"❌ outbound_service: {str(e)}")
test_results["total"] += 1

try:
    from simulation_service import get_available_scripts
    test_results["passed"] += 1
    test_results["details"].append("✅ simulation_service imported")
except Exception as e:
    test_results["failed"] += 1
    test_results["details"].append(f"❌ simulation_service: {str(e)}")
test_results["total"] += 1

for detail in test_results["details"]:
    print(detail)
print(f"\n📊 Import Status: {test_results['passed']}/{test_results['total']} passed\n")

# ============================================================================
# TEST 2: LANGUAGE SERVICE TESTS
# ============================================================================
print("\n🌐 TEST 2: LANGUAGE SERVICE FUNCTIONALITY")
print("-" * 80)

lang_tests = {"total": 0, "passed": 0, "failed": 0, "details": []}

try:
    from language_service import detect_language
    
    test_cases = [
        ("Hello, how can I help you?", "en"),
        ("வணக்கம், எப்படி உதவி செய்ய முடியும்?", "ta"),
        ("Hello da, naan help pannuven", "tanglish"),
    ]
    
    for text, expected in test_cases:
        lang_tests["total"] += 1
        result = detect_language(text)
        if result == expected:
            lang_tests["passed"] += 1
            lang_tests["details"].append(f"✅ Detected '{expected}' from: {text[:40]}...")
        else:
            lang_tests["failed"] += 1
            lang_tests["details"].append(f"❌ Expected '{expected}' but got '{result}' from: {text[:40]}...")
except Exception as e:
    lang_tests["failed"] += 1
    lang_tests["details"].append(f"❌ Language detection error: {str(e)}")
    lang_tests["total"] += 1

for detail in lang_tests["details"]:
    print(detail)
print(f"\n📊 Language Tests: {lang_tests['passed']}/{lang_tests['total']} passed\n")

# ============================================================================
# TEST 3: SENTIMENT SERVICE TESTS
# ============================================================================
print("\n😊 TEST 3: SENTIMENT SERVICE FUNCTIONALITY")
print("-" * 80)

sentiment_tests = {"total": 0, "passed": 0, "failed": 0, "details": []}

try:
    from sentiment_service import detect_sentiment
    
    test_cases = [
        ("This is terrible service!", "angry"),
        ("I'm frustrated with this", "frustrated"),
        ("Thank you so much!", "satisfied"),
        ("I want to cancel my service", "churn_risk"),
        ("Yes, that sounds good", "positive"),
    ]
    
    for text, expected_category in test_cases:
        sentiment_tests["total"] += 1
        try:
            result = detect_sentiment(text)
            if result.label == expected_category or expected_category in str(result.label):
                sentiment_tests["passed"] += 1
                sentiment_tests["details"].append(f"✅ Sentiment '{result.label}' (score: {result.score:.2f}) for: {text[:40]}...")
            else:
                sentiment_tests["failed"] += 1
                sentiment_tests["details"].append(f"⚠️  Got '{result.label}' (expected pattern '{expected_category}') for: {text[:40]}...")
        except Exception as e:
            sentiment_tests["failed"] += 1
            sentiment_tests["details"].append(f"❌ Error analyzing '{text}': {str(e)}")
except Exception as e:
    sentiment_tests["failed"] += 1
    sentiment_tests["details"].append(f"❌ Sentiment service error: {str(e)}")
    sentiment_tests["total"] += 1

for detail in sentiment_tests["details"]:
    print(detail)
print(f"\n📊 Sentiment Tests: {sentiment_tests['passed']}/{sentiment_tests['total']} passed\n")

# ============================================================================
# TEST 4: MEMORY SERVICE TESTS
# ============================================================================
print("\n💾 TEST 4: MEMORY SERVICE FUNCTIONALITY")
print("-" * 80)

memory_tests = {"total": 0, "passed": 0, "failed": 0, "details": []}

try:
    from memory_service import get_or_create_memory
    
    # Test creating and using memory
    session_id = "test_session_001"
    customer_id = "customer_123"
    
    memory_tests["total"] += 1
    memory = get_or_create_memory(session_id, customer_id)
    if memory:
        memory_tests["passed"] += 1
        memory_tests["details"].append(f"✅ Memory created for session: {session_id}")
    else:
        memory_tests["failed"] += 1
        memory_tests["details"].append(f"❌ Failed to create memory")
    
    # Test adding conversation turn
    memory_tests["total"] += 1
    try:
        memory.add_turn("user", "I have a billing issue", -0.5, "billing_inquiry", "en")
        memory_tests["passed"] += 1
        memory_tests["details"].append(f"✅ Added user turn to memory")
    except Exception as e:
        memory_tests["failed"] += 1
        memory_tests["details"].append(f"❌ Failed to add turn: {str(e)}")
    
    # Test getting sentiment trend
    memory_tests["total"] += 1
    try:
        memory.add_turn("assistant", "Let me help with that", 0.3, "support", "en")
        trend = memory.get_sentiment_trend()
        memory_tests["passed"] += 1
        memory_tests["details"].append(f"✅ Sentiment trend retrieved: {trend}")
    except Exception as e:
        memory_tests["failed"] += 1
        memory_tests["details"].append(f"❌ Failed to get trend: {str(e)}")

except Exception as e:
    memory_tests["failed"] += 1
    memory_tests["details"].append(f"❌ Memory service error: {str(e)}")

for detail in memory_tests["details"]:
    print(detail)
print(f"\n📊 Memory Tests: {memory_tests['passed']}/{memory_tests['total']} passed\n")

# ============================================================================
# TEST 5: OUTBOUND SERVICE TESTS
# ============================================================================
print("\n📞 TEST 5: OUTBOUND SERVICE FUNCTIONALITY")
print("-" * 80)

outbound_tests = {"total": 0, "passed": 0, "failed": 0, "details": []}

try:
    from outbound_service import start_outbound_call, OutboundCallScript
    
    outbound_tests["total"] += 1
    try:
        customer = {"name": "John Doe", "phone": "123456789"}
        session = start_outbound_call("renewal", customer)
        if session:
            outbound_tests["passed"] += 1
            outbound_tests["details"].append(f"✅ Outbound call session created for renewal")
        else:
            outbound_tests["failed"] += 1
            outbound_tests["details"].append(f"❌ Failed to create outbound session")
    except Exception as e:
        outbound_tests["failed"] += 1
        outbound_tests["details"].append(f"⚠️  Outbound session creation: {str(e)}")
    
    # Test script stages
    outbound_tests["total"] += 1
    try:
        script = OutboundCallScript("upsell", {"name": "Jane Smith"})
        stage = script.current_stage
        outbound_tests["passed"] += 1
        outbound_tests["details"].append(f"✅ Script initialized at stage: {stage}")
    except Exception as e:
        outbound_tests["failed"] += 1
        outbound_tests["details"].append(f"⚠️  Script creation: {str(e)}")

except Exception as e:
    outbound_tests["failed"] += 1
    outbound_tests["details"].append(f"❌ Outbound service error: {str(e)}")

for detail in outbound_tests["details"]:
    print(detail)
print(f"\n📊 Outbound Tests: {outbound_tests['passed']}/{outbound_tests['total']} passed\n")

# ============================================================================
# TEST 6: SIMULATION SERVICE TESTS
# ============================================================================
print("\n🎮 TEST 6: SIMULATION SERVICE FUNCTIONALITY")
print("-" * 80)

sim_tests = {"total": 0, "passed": 0, "failed": 0, "details": []}

try:
    from simulation_service import get_available_scripts
    
    sim_tests["total"] += 1
    scripts = get_available_scripts()
    if scripts and len(scripts) > 0:
        sim_tests["passed"] += 1
        script_names = [s.get("id") for s in scripts]
        sim_tests["details"].append(f"✅ Found {len(scripts)} simulation scripts: {', '.join(script_names)}")
    else:
        sim_tests["failed"] += 1
        sim_tests["details"].append(f"❌ No simulation scripts found")

except Exception as e:
    sim_tests["failed"] += 1
    sim_tests["details"].append(f"❌ Simulation service error: {str(e)}")

for detail in sim_tests["details"]:
    print(detail)
print(f"\n📊 Simulation Tests: {sim_tests['passed']}/{sim_tests['total']} passed\n")

# ============================================================================
# SUMMARY REPORT
# ============================================================================
print("\n" + "=" * 80)
print("🏁 TEST EXECUTION SUMMARY")
print("=" * 80)

all_passed = (test_results["passed"] + lang_tests["passed"] + sentiment_tests["passed"] +
              memory_tests["passed"] + outbound_tests["passed"] + sim_tests["passed"])
all_total = (test_results["total"] + lang_tests["total"] + sentiment_tests["total"] +
             memory_tests["total"] + outbound_tests["total"] + sim_tests["total"])

summary = {
    "Imports": f"{test_results['passed']}/{test_results['total']}",
    "Language Detection": f"{lang_tests['passed']}/{lang_tests['total']}",
    "Sentiment Analysis": f"{sentiment_tests['passed']}/{sentiment_tests['total']}",
    "Memory Service": f"{memory_tests['passed']}/{memory_tests['total']}",
    "Outbound Service": f"{outbound_tests['passed']}/{outbound_tests['total']}",
    "Simulation Service": f"{sim_tests['passed']}/{sim_tests['total']}",
}

for category, result in summary.items():
    print(f"  {category:<25} {result:>10}")

print(f"\n{'TOTAL':<25} {all_passed}/{all_total} passed")
success_rate = (all_passed / all_total * 100) if all_total > 0 else 0
print(f"{'Success Rate':<25} {success_rate:.1f}%")

if success_rate >= 80:
    print("\n✅ TESTING PASSED - System components functional!")
else:
    print("\n⚠️  TESTING INCOMPLETE - Some components need attention")

print("\n" + "=" * 80)
