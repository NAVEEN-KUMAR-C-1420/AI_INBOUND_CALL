"""
Outbound call orchestration and script management.
Handles renewal, upsell, and collections calls.
"""

from typing import Optional, List, Dict
from datetime import datetime


class OutboundCallScript:
    """Template for outbound calls with stages."""
    
    def __init__(self, call_type: str, customer_name: str, customer_id: str):
        self.call_type = call_type  # renewal, upsell, collections, churn_win_back
        self.customer_name = customer_name
        self.customer_id = customer_id
        self.current_stage = "opening"
        self.transcript: List[Dict] = []
        self.objections_raised = []
        self.outcome = None
        self.created_at = datetime.utcnow()
    
    def get_opening_line(self) -> str:
        """Get personalized opening line based on call type."""
        scripts = {
            "renewal": f"Hello {self.customer_name}, this is Sarah from TeleCorp UK. I'm calling because your contract is coming up for renewal next month and I have some great offers for you today.",
            "upsell": f"Hi {self.customer_name}, I noticed you might benefit from upgrading your plan. I have a special offer that could save you money and give you better service.",
            "collections": f"Hello {self.customer_name}, I'm calling regarding the outstanding balance on your account. I'd like to help you get this sorted today.",
            "churn_win_back": f"Hi {self.customer_name}, I see you're thinking about leaving us. Before you make a decision, I'd love to show you what we can do for you.",
        }
        return scripts.get(self.call_type, f"Hello {self.customer_name}, thanks for taking my call.")
    
    def get_stage_message(self, stage: str) -> str:
        """Get AI message for current stage."""
        
        # Generic stages for all call types
        stages = {
            "opening_wait": "I just need to pull up your details here...",
            "processing": "One moment please while I check our systems...",
            "hold": "Thank you for your patience, I'll be right back.",
        }
        
        # Call-type specific stages
        if self.call_type == "renewal":
            renewal_stages = {
                "opening": self.get_opening_line(),
                "pitch_new_plan": "Your current plan has been great, but I think we can offer you something even better with our new Business Plus package — unlimited data, EU roaming included, all for just £5 more per month.",
                "objection_price": "I understand cost is important. The additional £5 gives you double the data and priority support, which often saves businesses money in the long run by avoiding downtime.",
                "soft_close": "Shall I go ahead and set this up for you? Your new plan would start from next billing cycle, so there's no interruption.",
                "closing": "Perfect, {customer_name}. You're all set. You'll see the change reflected in next month's bill, and I'll send you a confirmation email shortly."
            }
            return renewal_stages.get(stage, stages.get(stage, "How can I help you further?"))
        
        elif self.call_type == "upsell":
            upsell_stages = {
                "opening": self.get_opening_line(),
                "feature_benefit": "I can see you're using 85% of your data allowance every month. Upgrading to our Pro plan gives you 3x the data and speeds of up to 150Mbps — perfect if your usage is growing.",
                "objection_need": "Many of our customers find higher data plans reduce frustration around throttling. Plus, for a just £10 more per month, it's often worth the peace of mind.",
                "closing": "Would you like me to make that change for you now? It takes just 60 seconds."
            }
            return upsell_stages.get(stage, stages.get(stage, "What else can I help with?"))
        
        elif self.call_type == "collections":
            collections_stages = {
                "opening": self.get_opening_line(),
                "amount_owed": "According to our system, you have an outstanding balance of £{amount} on your account. Can we work out a way to get this cleared today?",
                "payment_options": "I can offer you two options: either pay the full amount now, or we can set up a payment plan spread over 3 months with no extra charges.",
                "arrangement": "Great, let's set that up. I'll process the first payment today and send you confirmation to your registered email.",
                "closing": "Thank you {customer_name} for sorting this with us. Your account is now up to date."
            }
            return collections_stages.get(stage, stages.get(stage, "Is there anything else I can help with?"))
        
        return stages.get(stage, "How can I help you further?")
    
    def advance_stage(self) -> str:
        """Move to next stage and return next AI message."""
        stage_flow = {
            "renewal": ["opening", "pitch_new_plan", "objection_price", "soft_close", "closing"],
            "upsell": ["opening", "feature_benefit", "objection_need", "closing"],
            "collections": ["opening", "amount_owed", "payment_options", "arrangement", "closing"],
            "churn_win_back": ["opening", "objection_reason", "counter_offer", "closing"],
        }
        
        flow = stage_flow.get(self.call_type, [])
        current_idx = flow.index(self.current_stage) if self.current_stage in flow else -1
        
        if current_idx < len(flow) - 1:
            self.current_stage = flow[current_idx + 1]
        
        return self.get_stage_message(self.current_stage)
    
    def detect_objection(self, customer_response: str) -> Optional[str]:
        """Detect objection type from customer response."""
        response_lower = customer_response.lower()
        
        objection_patterns = {
            "price": ["expensive", "too much", "can't afford", "cost", "money", "cheaper", "better deal"],
            "need": ["don't need", "not interested", "don't use", "enough", "overkill"],
            "competitor": ["switch", "bt ", "vodafone", "ee ", "going elsewhere", "better service"],
            "timing": ["not now", "later", "think about", "discuss with", "call you back"],
            "service_concern": ["bad experience", "issues", "problems", "not working", "support"]
        }
        
        for objection_type, patterns in objection_patterns.items():
            if any(pattern in response_lower for pattern in patterns):
                if objection_type not in self.objections_raised:
                    self.objections_raised.append(objection_type)
                return objection_type
        
        return None
    
    def get_objection_response(self, objection_type: str) -> str:
        """Get response to specific objection."""
        responses = {
            "price": "I understand. Let me be clear about the value — with this plan, you're not just getting more data, you're also getting priority support and a 99.9% uptime guarantee.",
            "need": "That's fair. But looking at your usage over the last 3 months, I'm noticing you're hitting your limit pretty regularly. This upgrade would remove those concerns.",
            "competitor": "I appreciate you're shopping around. What if I could match their offer and add an extra month free? That would be better value, wouldn't it?",
            "timing": "I completely understand. How about this — I'll hold this offer for you until the end of this month. No obligation, but it means you have time to think it over.",
            "service_concern": "I'm sorry to hear you've had issues. Let's fix that right now. Can you tell me specifically what went wrong so I can address it personally?"
        }
        return responses.get(objection_type, "I hear your concern. Let me address that...")
    
    def end_call(self, outcome: str, notes: str = "") -> Dict:
        """End the call and return summary."""
        self.outcome = outcome  # succeeded, failed, partial
        return {
            "call_type": self.call_type,
            "customer_id": self.customer_id,
            "outcome": outcome,
            "objections": self.objections_raised,
            "stages_reached": len(self.transcript),
            "notes": notes,
            "duration": (datetime.utcnow() - self.created_at).total_seconds()
        }


# Outbound call session manager
_outbound_sessions: Dict[str, OutboundCallScript] = {}


def start_outbound_call(
    customer_id: str,
    customer_name: str,
    call_type: str
) -> Dict:
    """Start a new outbound call session."""
    script = OutboundCallScript(call_type, customer_name, customer_id)
    session_id = f"outbound_{customer_id}_{int(datetime.utcnow().timestamp())}"
    _outbound_sessions[session_id] = script
    
    return {
        "session_id": session_id,
        "customer_id": customer_id,
        "customer_name": customer_name,
        "call_type": call_type,
        "opening_line": script.get_opening_line(),
        "stage": script.current_stage
    }


def get_outbound_session(session_id: str) -> Optional[OutboundCallScript]:
    """Retrieve outbound call session."""
    return _outbound_sessions.get(session_id)


def process_customer_response(session_id: str, response_text: str) -> Dict:
    """Process customer response and advance script."""
    script = _outbound_sessions.get(session_id)
    if not script:
        return {"error": "Session not found"}
    
    # Detect any objections
    objection = script.detect_objection(response_text)
    
    # Record in transcript
    script.transcript.append({
        "who": "customer",
        "text": response_text,
        "objection": objection,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    # Generate response
    if objection:
        ai_response = script.get_objection_response(objection)
    else:
        ai_response = script.advance_stage()
    
    script.transcript.append({
        "who": "ai",
        "text": ai_response,
        "stage": script.current_stage,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {
        "ai_response": ai_response,
        "stage": script.current_stage,
        "objection_detected": objection,
        "call_active": script.current_stage != "closing"
    }


def end_outbound_call(session_id: str, outcome: str, notes: str = "") -> Dict:
    """End outbound call session."""
    script = _outbound_sessions.get(session_id)
    if not script:
        return {"error": "Session not found"}
    
    summary = script.end_call(outcome, notes)
    del _outbound_sessions[session_id]
    
    return summary
