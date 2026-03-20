/**
 * TypeScript interfaces for the entire call center application.
 */

// Language types
export type Language = "en" | "ta" | "tanglish";

// Sentiment levels
export type SentimentLabel = "angry" | "frustrated" | "mildly_frustrated" | "neutral" | "satisfied" | "positive";

// Call types
export type CallMode = "inbound" | "outbound" | "simulation";
export type CallStatus = "idle" | "ringing" | "active" | "on_hold" | "ended";

// ============================================================
// CUSTOMER & ACCOUNT
// ============================================================
export interface Customer {
  id: string;
  full_name: string;
  phone: string;
  email: string;
  plan_id?: string;
  plan_name?: string;
  monthly_fee_gbp?: number;
  outstanding_balance_gbp?: number;
  data_usage_percent?: number;
  account_status?: "active" | "suspended" | "pending_cancellation";
  churn_risk_score?: number;
  upsell_score?: number;
  call_history_count?: number;
  last_call_date?: string | null;
  last_call_intent?: string | null;
  last_call_resolved?: boolean | null;
  repeat_issue?: boolean;
  tags?: string[];
  language_preference?: Language;
  lifetime_value_gbp?: number;
  nps_score?: number | null;
  company_name?: string;
  job_title?: string;
}

// ============================================================
// MESSAGING & TRANSCRIPTS
// ============================================================
export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: string;
  language?: Language;
  speaker?: "customer" | "agent" | "ai";
  interim?: boolean;  // for streaming transcripts
}

// ============================================================
// SENTIMENT & ANALYSIS
// ============================================================
export interface SentimentResult {
  label: SentimentLabel;
  score: number;  // -1.0 to 1.0
  trajectory: "worsening" | "stable" | "improving";
  trigger_phrase: string | null;
  churn_risk: boolean;
  escalation_needed: boolean;
}

export interface SentimentUpdate {
  sentiment: SentimentLabel;
  score: number;
  trajectory: string;
  urgency: "low" | "medium" | "high";
  churn_alert?: boolean;
  escalation_alert?: boolean;
}

// ============================================================
// AI SUGGESTIONS
// ============================================================
export type SuggestionTone = "empathetic" | "informational" | "persuasive" | "assertive";

export interface Suggestion {
  rank: 1 | 2 | 3;
  text: string;
  tone: SuggestionTone;
  resolution_likelihood: number;  // 0.0 to 1.0
  is_de_escalation: boolean;
  context_ref?: string;
}

export interface RAGSource {
  intent_id: string;
  relevance_score: number;
  answer_preview: string;
}

// ============================================================
// AI RESPONSES
// ============================================================
export interface AIUpdate {
  response: string;
  intent: string;
  sentiment: SentimentLabel;
  sentiment_score: number;
  urgency: "low" | "medium" | "high";
  trajectory: string;
  trigger_phrase: string | null;
  churn_risk: boolean;
  escalation_needed: boolean;
  suggestions: Suggestion[];
  language: Language;
  language_detected: Language;
  de_escalation: string | null;
  rag_sources: RAGSource[];
  abusive_language_detected?: boolean;
  angry_turns?: number;  // count of consecutive angry sentiment turns
}

// ============================================================
// CALL SUMMARY & OUTCOMES
// ============================================================
export interface CallSummary {
  id?: string;
  summary: string;
  issue: string;
  sentiment: SentimentLabel;
  resolution: "resolved" | "unresolved" | "escalated";
  recommended_action: string;
  csat_prediction: number;  // 1-10
  duration_seconds?: number;
  transcript?: Message[];
}

export interface CallOutcome {
  session_id: string;
  customer_id: string;
  resolution: "resolved" | "unresolved" | "escalated";
  notes?: string;
  agent_id?: string;
  timestamp?: string;
}

// ============================================================
// CALL SESSIONS
// ============================================================
export interface CallSession {
  id: string;
  customer: Customer | null;
  transcript: Message[];
  sentimentArc: number[];  // array of sentiment scores through call
  languageHistory: Language[];
  intent: string;
  urgency: "low" | "medium" | "high";
  escalationNeeded: boolean;
  isActive: boolean;
  callType: CallMode;
  callStatus: CallStatus;
  startTime: Date | null;
  endTime?: Date;
  duration?: number;  // seconds
  isEscalated?: boolean;
  aiSilent?: boolean;  // if true, AI is not speaking
  abusiveLanguageDetected?: boolean;
  humanTakeoverActive?: boolean;
}

// ============================================================
// ESCALATION & HUMAN TAKEOVER
// ============================================================
export interface EscalationAlert {
  type: "warning" | "critical";
  message: string;
  department?: string;
  eta?: number;  // minutes wait time
  reason?: string;
}

export interface HumanTakeoverState {
  active: boolean;
  started_at?: string;
  agent_id?: string;
  escalation_reason?: string;
  department?: string;
}

// ============================================================
// SIMULATION
// ============================================================
export interface SimulationTurn {
  turn_number: number;
  total_turns: number;
  speaker: "customer" | "agent" | "agent_opening" | "system";
  text: string;
  expected_intent?: string;
  expected_sentiment?: SentimentLabel;
  language?: Language;
  completed: boolean;
}

export interface SimulationScript {
  script_id: string;
  scenario_name: string;
  difficulty: "easy" | "medium" | "hard";
  learning_objectives: string[];
  turn_count: number;
}

export interface SimulationAccuracy {
  total_turns: number;
  intent_accuracy: number;
  sentiment_accuracy: number;
  intents_tested: number;
  sentiments_tested: number;
}

// ============================================================
// OUTBOUND CALLS
// ============================================================
export type OutboundCallType = "renewal" | "upsell" | "collections" | "churn_win_back";
export type OutboundStage = "opening" | "pitch" | "objection" | "closing" | "completed";
export type OutboundOutcome = "succeeded" | "failed" | "partial";

export interface OutboundCallSession {
  session_id: string;
  customer_id: string;
  customer_name: string;
  call_type: OutboundCallType;
  current_stage: OutboundStage;
  opening_line: string;
  objections: string[];
  outcome?: OutboundOutcome;
  transcript: Message[];
}

// ============================================================
// DASHBOARD & ANALYTICS
// ============================================================
export interface MetricCard {
  label: string;
  value: string | number;
  trend?: "up" | "down" | "neutral";
  trend_value?: number;
}

export interface CallMetrics {
  calls_today: number;
  avg_handle_time: number;  // seconds
  fcr_rate: number;  // first call resolution %
  csat_avg: number;  // customer satisfaction
  churn_risk_count: number;
  escalations_today: number;
}

// ============================================================
// COMPONENT STATE
// ============================================================
export interface AppState {
  currentView: "dashboard" | "inbound" | "outbound" | "simulation";
  callSession: CallSession | null;
  aiUpdate: AIUpdate | null;
  isProcessing: boolean;
  globalLanguage: Language;
}

export interface TranscriptPanelProps {
  transcript: Message[];
  isProcessing: boolean;
  triggerPhrases?: string[];
  onSendText?: (text: string) => void;
}

export interface SentimentMeterProps {
  sentiment: SentimentLabel;
  score: number;
  trajectory: string;
  trigger_phrase: string | null;
  churn_risk: boolean;
  escalation_needed: boolean;
  arc: number[];  // sentiment history
}

export interface SuggestionCardsProps {
  suggestions: Suggestion[];
  onUse: (text: string) => void;
  isLoading: boolean;
  aiSilent?: boolean;
}

// ============================================================
// API REQUESTS & RESPONSES
// ============================================================
export interface ChatRequestPayload {
  messages: Message[];
  customer?: Customer | null;
  session_id?: string;
  language_history?: Language[];
}

export interface IdentifyRequestPayload {
  name?: string;
  phone?: string;
}

export interface SummaryRequestPayload {
  transcript: Message[];
  session_id?: string;
  customer_phone?: string;
}

export interface OutboundCallRequestPayload {
  customer_id: string;
  call_purpose: OutboundCallType;
  agent_mode?: "assisted" | "autonomous";
}

export interface SimulationStartPayload {
  script_id: string;
}

// ============================================================
// WEBSOCKET MESSAGES
// ============================================================
export interface WSMessage {
  type: "audio_chunk" | "user_message" | "end_call" | "escalate" | "restore_ai";
  data?: any;
}

export interface WSMessageUpdate {
  type: "transcript_update" | "ai_update" | "call_summary" | "sentiment_change" | "escalation";
  data: any;
}

// ============================================================
// UI STATE & HOOKS
// ============================================================
export interface SpeechRecognitionState {
  isListening: boolean;
  transcript: string;
  interimTranscript: string;
  error: string | null;
  language: Language;
}

export interface TextToSpeechState {
  isSpeaking: boolean;
  currentText: string | null;
}

export interface CallSessionHookState {
  session: CallSession;
  aiUpdate: AIUpdate | null;
  summary: CallSummary | null;
  stage: "idle" | "identifying" | "active" | "ended";
  isProcessing: boolean;
  isEscalated: boolean;
  escalationInfo: EscalationAlert | null;
  aiSilent: boolean;
}
