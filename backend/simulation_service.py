"""
Call simulation service for demo/training purposes.
Pre-scripted realistic call scenarios.
"""

from typing import Optional, List, Dict
from datetime import datetime


class SimulationScript:
    """A scripted call scenario for training/demo."""
    
    def __init__(self, script_id: str, scenario_name: str, turns_data: List[Dict]):
        self.script_id = script_id
        self.scenario_name = scenario_name
        self.turns = turns_data  # List of {speaker, text, expected_intent?, expected_sentiment?}
        self.current_turn_idx = 0
        self.transcript: List[Dict] = []
        self.completed = False
        self.created_at = datetime.utcnow()
    
    def get_current_turn(self) -> Optional[Dict]:
        """Get current turn to display."""
        if self.current_turn_idx >= len(self.turns):
            return None
        
        turn = self.turns[self.current_turn_idx]
        return {
            "turn_number": self.current_turn_idx + 1,
            "total_turns": len(self.turns),
            "speaker": turn.get("speaker"),  # customer, agent, system
            "text": turn.get("text"),
            "expected_intent": turn.get("expected_intent"),
            "expected_sentiment": turn.get("expected_sentiment"),
            "language": turn.get("language", "en")
        }
    
    def advance_turn(self, actual_analysis: Optional[Dict] = None) -> bool:
        """
        Advance to next turn.
        Track actual vs expected analysis if provided.
        Returns True if more turns exist.
        """
        if self.current_turn_idx < len(self.turns):
            current = self.turns[self.current_turn_idx]
            
            # Record analysis results
            if actual_analysis:
                current["actual_intent"] = actual_analysis.get("intent")
                current["actual_sentiment"] = actual_analysis.get("sentiment")
                current["ai_response"] = actual_analysis.get("response")
            
            self.transcript.append(current)
            self.current_turn_idx += 1
            
            if self.current_turn_idx >= len(self.turns):
                self.completed = True
                return False
            
            return True
        
        return False
    
    def get_accuracy_report(self) -> Dict:
        """Compare actual vs expected analysis."""
        intent_correct = 0
        sentiment_correct = 0
        total_predictions = 0
        
        for turn in self.transcript:
            if turn.get("expected_intent"):
                total_predictions += 1
                if turn.get("actual_intent") == turn.get("expected_intent"):
                    intent_correct += 1
            
            if turn.get("expected_sentiment"):
                if turn.get("actual_sentiment") == turn.get("expected_sentiment"):
                    sentiment_correct += 1
        
        return {
            "total_turns": len(self.transcript),
            "intent_accuracy": intent_correct / max(total_predictions, 1),
            "sentiment_accuracy": sentiment_correct / max(total_predictions, 1),
            "intents_tested": total_predictions,
            "sentiments_tested": sum(1 for t in self.transcript if t.get("expected_sentiment")),
        }


# Pre-defined simulation scripts
SIMULATION_SCRIPTS = {
    "inbound_billing": {
        "scenario_name": "Inbound: Billing Dispute (Jane Smith - Repeat Caller)",
        "difficulty": "medium",
        "learning_objectives": [
            "Detect billing intent from customer anger",
            "Recognize repeat caller pattern",
            "Escalate appropriately when sentiment worsens"
        ],
        "turns": [
            {
                "speaker": "customer",
                "text": "Hi, I've been charged twice this month and my signal has been terrible all week. I'm honestly thinking of just cancelling.",
                "expected_intent": "billing_dispute",
                "expected_sentiment": "frustrated",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "I'm so sorry to hear that. Let me pull up your account immediately and look into both the double charge and the signal issue.",
            },
            {
                "speaker": "customer",
                "text": "The charge was on the 1st and 15th of March, both for £15. And I live in London, postcode EC1A 1BB.",
                "expected_sentiment": "frustrated",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "",  # AI will generate response
            },
            {
                "speaker": "customer",
                "text": "I've already called about this twice and nothing was fixed. I'm seriously thinking of switching to BT.",
                "expected_intent": "churn_risk",
                "expected_sentiment": "angry",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "",  # AI will generate - should de-escalate
            },
            {
                "speaker": "customer",
                "text": "Okay, if you can give me a discount I'll stay for now.",
                "expected_sentiment": "neutral",
                "language": "en"
            }
        ]
    },
    
    "outbound_renewal": {
        "scenario_name": "Outbound: Contract Renewal (John Doe - Upsell)",
        "difficulty": "easy",
        "learning_objectives": [
            "Practice opening lines for outbound calls",
            "Detect objections to offers",
            "Handle price sensitivity"
        ],
        "turns": [
            {
                "speaker": "agent_opening",
                "text": "Hello John, this is Sarah from TeleCorp UK. I'm calling because your contract is up for renewal next month and I have a special offer for you today.",
            },
            {
                "speaker": "customer",
                "text": "Oh okay, what kind of offer?",
                "expected_sentiment": "neutral",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "I can see you're on our SIM Only plan at £15/month. We have a new Business Mobile plan at just £25/month that gives you unlimited everything — data, calls, texts, plus EU roaming included.",
            },
            {
                "speaker": "customer",
                "text": "That sounds quite expensive actually. I don't really use that much data.",
                "expected_intent": "plan_downgrade",
                "expected_sentiment": "mildly_frustrated",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "I understand cost is a concern. But actually, if you look at your usage patterns over the last 3 months, you've been hitting your limit regularly. With unlimited data, you'd never have to worry about throttling again.",
            },
            {
                "speaker": "customer",
                "text": "Alright, go ahead and set it up then.",
                "expected_sentiment": "positive",
                "language": "en"
            }
        ]
    },
    
    "inbound_tamil": {
        "scenario_name": "Inbound: Tamil Speaker - Network Issue (Rajesh Kumar)",
        "difficulty": "hard",
        "learning_objectives": [
            "Detect and respond to Tamil language input",
            "Understand code-mixed (Tanglish) responses",
            "Handle network outage with multilingual support"
        ],
        "turns": [
            {
                "speaker": "customer",
                "text": "என் வீட்டில் signal இல்லை, என்ன பண்றது?",
                "expected_intent": "network_outage",
                "expected_sentiment": "frustrated",
                "language": "tamil"
            },
            {
                "speaker": "agent",
                "text": "வணக்கம், உங்கள் சிக்கலை நான் தீர்க்கிறேன்.",
            },
            {
                "speaker": "customer",
                "text": "Morning from 8 o'clock la signal pochu. Postcode EC1A 1BB. Seri fix pannuven na?",
                "expected_sentiment": "frustrated",
                "language": "tanglish"
            },
            {
                "speaker": "agent",
                "text": "Understood sir. Let me check network status for your area right now.",
            },
            {
                "speaker": "customer",
                "text": "Okay thank you. When will it be fixed?",
                "expected_sentiment": "neutral",
                "language": "en"
            }
        ]
    },
    
    "collections_follow_up": {
        "scenario_name": "Collections: Payment Follow-up (Lisa Brown - Outstanding Balance)",
        "difficulty": "medium",
        "learning_objectives": [
            "Approach collections calls with empathy",
            "Recognize when to offer payment plans",
            "De-escalate defensive/hostile reactions"
        ],
        "turns": [
            {
                "speaker": "agent_opening",
                "text": "Hello Lisa, I'm calling regarding the outstanding balance on your TeleCorp account. I'd like to help you get this sorted.",
            },
            {
                "speaker": "customer",
                "text": "Look, I'm in between jobs right now, I can't pay the full amount if that's what you're calling about.",
                "expected_sentiment": "mildly_frustrated",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "I completely understand. I'm not asking for full payment today. Let me offer you a payment plan — we can split this over 3 months with no extra charges.",
            },
            {
                "speaker": "customer",
                "text": "Three months? How much would each payment be?",
                "expected_sentiment": "neutral",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "Your outstanding balance is £147. Over 3 months, that's £49 per month, starting from next week.",
            },
            {
                "speaker": "customer",
                "text": "Yeah, okay, I can do that. When do I start?",
                "expected_sentiment": "positive",
                "language": "en"
            }
        ]
    },

    "churn_recovery": {
        "scenario_name": "Win-back: Churn Recovery (Michael Green - Wants to Leave)",
        "difficulty": "hard",
        "learning_objectives": [
            "Recognize churn language patterns early",
            "Offer retention deals strategically",
            "Know when to escalate vs. push harder"
        ],
        "turns": [
            {
                "speaker": "customer",
                "text": "Hi, yeah... I'm looking to cancel my contract. Your service has been really unreliable.",
                "expected_intent": "churn_risk",
                "expected_sentiment": "frustrated",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "I'm really sorry to hear that, Michael. Before you make any decisions, can I look into what's gone wrong? I might be able to make this right.",
            },
            {
                "speaker": "customer",
                "text": "Honestly, I've had outages 3 times in the last month. I'm going to switch to Vodafone.",
                "expected_intent": "churn_risk",
                "expected_sentiment": "angry",
                "language": "en"
            },
            {
                "speaker": "agent",
                "text": "Those outages are unacceptable, and I sincerely apologize. I want to make this right. I can offer you 3 months free service as compensation, plus an upgrade to our Pro broadband at no extra cost.",
            },
            {
                "speaker": "customer",
                "text": "Hmm... 3 months free? That's pretty good. Can you send me details?",
                "expected_sentiment": "neutral",
                "language": "en"
            }
        ]
    }
}


# Runtime simulation sessions
_sim_sessions: Dict[str, SimulationScript] = {}


def get_available_scripts() -> List[Dict]:
    """Get list of available simulation scripts."""
    return [
        {
            "script_id": script_id,
            "scenario_name": data["scenario_name"],
            "difficulty": data.get("difficulty", "medium"),
            "learning_objectives": data.get("learning_objectives", []),
            "turn_count": len(data["turns"])
        }
        for script_id, data in SIMULATION_SCRIPTS.items()
    ]


def start_simulation(script_id: str) -> Dict:
    """Start a new simulation session."""
    if script_id not in SIMULATION_SCRIPTS:
        return {"error": f"Script {script_id} not found"}
    
    script_data = SIMULATION_SCRIPTS[script_id]
    script = SimulationScript(
        script_id,
        script_data["scenario_name"],
        script_data["turns"]
    )
    
    session_id = f"sim_{script_id}_{int(datetime.utcnow().timestamp())}"
    _sim_sessions[session_id] = script
    
    return {
        "session_id": session_id,
        "script_id": script_id,
        "scenario": script_data["scenario_name"],
        "difficulty": script_data.get("difficulty", "medium"),
        "total_turns": len(script_data["turns"]),
        "first_turn": script.get_current_turn()
    }


def get_sim_session(session_id: str) -> Optional[SimulationScript]:
    """Retrieve simulation session."""
    return _sim_sessions.get(session_id)


def get_next_sim_turn(session_id: str) -> Dict:
    """Get next turn in simulation."""
    script = _sim_sessions.get(session_id)
    if not script:
        return {"error": "Session not found"}
    
    # Advance to next turn
    has_more = script.advance_turn()
    
    if not has_more:
        # Simulation complete
        accuracy = script.get_accuracy_report()
        return {
            "completed": True,
            "accuracy_report": accuracy,
            "transcript": script.transcript
        }
    
    # Return next turn
    current_turn = script.get_current_turn()
    return {
        "completed": False,
        **(current_turn or {})
    }


def submit_sim_analysis(
    session_id: str,
    turn_number: int,
    analysis: Dict
) -> Dict:
    """
    Submit AI analysis for current turn.
    Returns comparison of actual vs expected.
    """
    script = _sim_sessions.get(session_id)
    if not script:
        return {"error": "Session not found"}
    
    turn_idx = turn_number - 1
    if turn_idx < 0 or turn_idx >= len(script.transcript):
        return {"error": "Invalid turn number"}
    
    turn = script.transcript[turn_idx]
    
    results = {
        "turn": turn_number,
        "predictions": analysis,
        "expected": {
            "intent": turn.get("expected_intent"),
            "sentiment": turn.get("expected_sentiment")
        },
        "accuracy": {}
    }
    
    if turn.get("expected_intent"):
        results["accuracy"]["intent"] = (
            analysis.get("intent") == turn.get("expected_intent")
        )
    
    if turn.get("expected_sentiment"):
        results["accuracy"]["sentiment"] = (
            analysis.get("sentiment") == turn.get("expected_sentiment")
        )
    
    return results


def end_simulation(session_id: str) -> Dict:
    """End simulation and return final report."""
    script = _sim_sessions.get(session_id)
    if not script:
        return {"error": "Session not found"}
    
    report = script.get_accuracy_report()
    del _sim_sessions[session_id]
    
    return {
        "scenario": script.scenario_name,
        "turns_played": script.current_turn_idx,
        "accuracy_report": report,
        "transcript": script.transcript
    }
