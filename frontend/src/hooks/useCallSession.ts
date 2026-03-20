/**
 * Hook for managing core call session state.
 * Handles call flow, messaging, escalation, and AI silent mode.
 */

import { useState, useCallback, useRef } from "react";
import * as Types from "../types";
import * as api from "../services/api";

function normalizeLanguage(value?: string): Types.Language {
  if (value === "ta") return "ta";
  if (value === "tanglish") return "tanglish";
  return "en";
}

function normalizeUrgency(value?: string): "low" | "medium" | "high" {
  if (value === "high" || value === "medium" || value === "low") return value;
  return "low";
}

function normalizeSentiment(value?: string): Types.SentimentLabel {
  if (
    value === "angry" ||
    value === "frustrated" ||
    value === "mildly_frustrated" ||
    value === "neutral" ||
    value === "satisfied" ||
    value === "positive"
  ) {
    return value;
  }
  return "neutral";
}

export function useCallSession() {
  const sessionIdRef = useRef<string>(`session_${Date.now()}`);
  
  const [session, setSession] = useState<Types.CallSession | null>(null);
  const [aiUpdate, setAiUpdate] = useState<Types.AIUpdate | null>(null);
  const [summary, setSummary] = useState<Types.CallSummary | null>(null);
  const [stage, setStage] = useState<"idle" | "identifying" | "active" | "ended">("idle");
  const [isProcessing, setIsProcessing] = useState(false);
  const [isEscalated, setIsEscalated] = useState(false);
  const [escalationInfo, setEscalationInfo] = useState<Types.EscalationAlert | null>(null);
  const [aiSilent, setAiSilent] = useState(false);

  const autoEscalationSentRef = useRef(false);

  /**
   * Start a new call with selected customer.
   */
  const startCall = useCallback((customer: Types.Customer, callType: Types.CallMode = "inbound") => {
    const newSessionId = `session_${Date.now()}`;
    sessionIdRef.current = newSessionId;

    const newSession: Types.CallSession = {
      id: newSessionId,
      customer,
      transcript: [],
      sentimentArc: [],
      languageHistory: customer.language_preference ? [customer.language_preference] : ["en"],
      intent: "general",
      urgency: "low",
      escalationNeeded: false,
      isActive: true,
      callType,
      callStatus: "active",
      startTime: new Date(),
    };

    setSession(newSession);
    setStage("active");
    setIsEscalated(false);
    setAiSilent(false);
    setEscalationInfo(null);
    autoEscalationSentRef.current = false;
  }, []);

  /**
   * Send customer message and get AI response.
   */
  const sendMessage = useCallback(
    async (text: string) => {
      if (!session?.customer || isProcessing) return;

      // Add customer message to transcript
      const userMessage: Types.Message = {
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      };

      setSession((prev) => 
        prev ? {
          ...prev,
          transcript: [...prev.transcript, userMessage],
        } : null
      );

      setIsProcessing(true);

      try {
        // Call AI endpoint using existing MessageRequest pattern
        const callId = Number.parseInt(session.id, 10);
        if (!Number.isFinite(callId) || callId <= 0) {
          throw new Error("Invalid call id for sendMessage");
        }
        const response = await api.apiService.sendMessage(callId, text);

        // Update sentiment arc
        setSession((prev) => 
          prev ? {
            ...prev,
            sentimentArc: [...prev.sentimentArc, response.urgency === "high" ? -0.8 : 0],
            intent: response.intent || "general",
            urgency: normalizeUrgency(response.urgency),
            languageHistory: response.language_mode
              ? [...prev.languageHistory, normalizeLanguage(response.language_mode)]
              : prev.languageHistory,
          } : null
        );

        // Add AI response to transcript
        const aiMessage: Types.Message = {
          role: "assistant",
          content: response.ai_response || "",
          timestamp: new Date().toISOString(),
          language: normalizeLanguage(response.language_mode),
        };

        setSession((prev) => 
          prev ? {
            ...prev,
            transcript: [...prev.transcript, aiMessage],
            escalationNeeded: response.escalation_alert || false,
          } : null
        );

        // Handle auto-escalation
        if (response.escalation_alert && !autoEscalationSentRef.current) {
          autoEscalationSentRef.current = true;
          setIsEscalated(true);
          setEscalationInfo({
            type: "critical",
            message: `Escalation triggered: ${response.trigger_phrases?.[0] || "Customer sentiment critical"}`,
            department: response.urgency === "high" ? "supervisor" : "support",
          });
          setAiSilent(false);
        }

        // Store response for display
        setAiUpdate(response as any);
      } catch (error) {
        console.error("Chat error:", error);
        setAiUpdate({
          response: "I'm sorry, I encountered a technical issue. Let me try that again.",
          intent: "error",
          sentiment: "neutral",
          sentiment_score: 0,
          urgency: "low",
          trajectory: "stable",
          trigger_phrase: null,
          churn_risk: false,
          escalation_needed: false,
          suggestions: [],
          language: "en",
          language_detected: "en",
          de_escalation: null,
          rag_sources: [],
        });
      } finally {
        setIsProcessing(false);
      }
    },
    [session, isProcessing]
  );

  /**
   * End current call and generate summary.
   */
  const endCall = useCallback(async () => {
    if (!session) return;

    setSession((prev) => 
      prev ? {
        ...prev,
        isActive: false,
        callStatus: "ended" as const,
        endTime: new Date(),
      } : null
    );

    setStage("ended");

    try {
      // Call the summary endpoint for this call_id
      const callSummary = await api.apiService.getSummary(
        parseInt(session.id) || 0
      );
      
      // Map Summary to CallSummary type
      setSummary({
        summary: callSummary.summary,
        issue: callSummary.issue,
        sentiment: normalizeSentiment(callSummary.sentiment),
        recommended_action: callSummary.action,
        resolution: callSummary.resolved ? "resolved" : "unresolved",
        csat_prediction: callSummary.resolved ? 0.8 : 0.4,
      });

      // Save outcome
      if (session.customer) {
        const customerId = typeof session.customer.id === "string" 
          ? parseInt(session.customer.id) 
          : session.customer.id;
          
        await api.apiService.saveOutcome(
          session.id,
          customerId,
          isEscalated ? "escalated" : (callSummary.resolved ? "resolved" : "unresolved")
        );
      }
    } catch (error) {
      console.error("Summary generation error:", error);
    }
  }, [session, isEscalated]);

  /**
   * Restore AI control (after human takeover escalation).
   */
  const restoreAI = useCallback(async () => {
    try {
      if (session?.id) {
        await api.apiService.resolveEscalation(session.id);
      }
      setIsEscalated(false);
      setAiSilent(false);
      setEscalationInfo(null);
      autoEscalationSentRef.current = false;
    } catch (error) {
      console.error("Failed to restore AI:", error);
    }
  }, [session?.id]);

  /**
   * Reset session for next call.
   */
  const resetSession = useCallback(() => {
    setSession(null);
    setAiUpdate(null);
    setSummary(null);
    setStage("idle");
    setIsEscalated(false);
    setAiSilent(false);
    setEscalationInfo(null);
    autoEscalationSentRef.current = false;
  }, []);

  return {
    session,
    aiUpdate,
    summary,
    stage,
    isProcessing,
    isEscalated,
    escalationInfo,
    aiSilent,
    startCall,
    sendMessage,
    endCall,
    restoreAI,
    resetSession,
  };
}
