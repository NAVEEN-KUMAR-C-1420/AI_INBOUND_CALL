import axios from 'axios';

const API_BASE = 'http://localhost:8030';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface Customer {
  id: number;
  name: string;
  phone: string;
  plan: string;
}

export interface CustomerCreatePayload {
  name: string;
  phone: string;
  plan?: string;
}

export interface Call {
  id: number;
  customer_id: number;
  start_time: string;
  status: string;
}

export interface MessageResponse {
  ai_response: string;
  intent: string;
  sentiment: string;
  urgency: string;
  language_mode?: string;
  escalation_alert?: boolean;
  trigger_phrases?: string[];
  suggestions?: Array<{ suggestion: string; tone: string }>;
}

export interface ConversationItem {
  speaker: string;
  message: string;
  timestamp: string;
  intent?: string;
  sentiment?: string;
}

export interface Summary {
  summary: string;
  issue: string;
  sentiment: string;
  resolved: boolean;
  action: string;
  compliance: string;
  decision: string;
}

export interface SummaryResult {
  summary: string;
  issue: string;
  sentiment: string;
  resolution: string;
  recommended_action: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatRequestPayload {
  messages: ChatMessage[];
  customer_name?: string;
  customer_phone?: string;
  customer?: Record<string, unknown>;
  language_history?: string[];
  session_id?: string;
}

export interface ChatResponse {
  response: string;
  ai_response?: string;
  intent: string;
  sentiment: string;
  sentiment_score?: number;
  urgency: string;
  trajectory?: 'worsening' | 'stable' | 'improving' | string;
  trigger_phrase?: string | null;
  trigger_phrases?: string[];
  churn_risk?: boolean;
  escalation_needed?: boolean;
  escalation_alert?: boolean;
  auto_escalated?: boolean;
  angry_turns?: number;
  language?: string;
  language_mode?: string;
  language_detected?: string;
  de_escalation?: string | null;
  rag_sources?: unknown[];
  memory_context?: string;
  session_id?: string;
  timestamp?: string;
}

export interface Memory {
  issue: string;
  status: string;
  sentiment?: string;
  resolution?: string;
  created_at: string;
}

export interface CallHistoryItem {
  id: number;
  start_time: string;
  end_time?: string | null;
  status: string;
  summary?: string | null;
  issue?: string | null;
  resolved?: boolean | null;
}

export interface SaveOutcomeResponse {
  success: boolean;
  message?: string;
}

export interface ResolveEscalationResponse {
  success: boolean;
  message?: string;
}

export interface OutboundStartRequest {
  customer_id: string;
  call_purpose: 'renewal' | 'upsell' | 'collections' | 'churn_win_back' | string;
}

export interface OutboundRespondRequest {
  session_id: string;
  response: string;
}

export interface OutboundEndRequest {
  session_id: string;
  outcome?: 'succeeded' | 'failed' | 'partial' | string;
  notes?: string;
}

export function openWebSocket(sessionId: string): WebSocket {
  const wsBase = API_BASE.replace(/^http/i, 'ws');
  return new WebSocket(`${wsBase}/ws/${encodeURIComponent(sessionId)}`);
}

export function sendWSMessage(ws: WebSocket, message: unknown): void {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(message));
  }
}

export const apiService = {
  // Health check
  async checkHealth(): Promise<{ status: string; ollama: string; client_id?: string; client_name?: string }> {
    const response = await api.get('/health');
    return response.data;
  },

  // Customers
  async getCustomers(): Promise<Customer[]> {
    const response = await api.get('/customers');
    return response.data;
  },

  async getCustomer(id: number): Promise<Customer> {
    const response = await api.get(`/customers/${id}`);
    return response.data;
  },

  async createCustomer(payload: CustomerCreatePayload): Promise<Customer> {
    const response = await api.post('/customers', {
      name: payload.name,
      phone: payload.phone,
      plan: payload.plan || 'Basic',
    });
    return response.data;
  },

  async getCustomerMemory(customerId: number): Promise<Memory[]> {
    const response = await api.get(`/customers/${customerId}/memory`);
    return response.data;
  },

  async getCustomerCalls(customerId: number): Promise<CallHistoryItem[]> {
    const response = await api.get(`/customers/${customerId}/calls`);
    return response.data;
  },

  // Calls
  async startCall(customerId: number): Promise<Call> {
    const response = await api.post('/calls/start', { customer_id: customerId });
    return response.data;
  },

  async sendMessage(callId: number, message: string): Promise<MessageResponse> {
    const response = await api.post(`/calls/${callId}/message`, {
      call_id: callId,
      message,
    });
    return response.data;
  },

  async endCall(callId: number): Promise<Summary> {
    const response = await api.post(`/calls/${callId}/end`);
    return response.data;
  },

  async getTranscript(callId: number): Promise<ConversationItem[]> {
    const response = await api.get(`/calls/${callId}/transcript`);
    return response.data;
  },

  async getSummary(callId: number): Promise<Summary> {
    const response = await api.get(`/calls/${callId}/summary`);
    return response.data;
  },

  async generateSummary(
    transcript: Array<{ role: string; content: string }>,
    sessionId: string,
    customerPhone?: string
  ): Promise<SummaryResult> {
    const response = await fetch(`${API_BASE}/api/summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        transcript: transcript || [],
        session_id: sessionId,
        customer_phone: customerPhone,
      }),
    });

    if (!response.ok) {
      throw new Error(`Summary failed: ${response.statusText}`);
    }

    return response.json();
  },

  async chat(payload: ChatRequestPayload): Promise<ChatResponse> {
    const response = await api.post('/api/chat', payload);
    return response.data;
  },

  async getScripts(): Promise<Array<Record<string, unknown>>> {
    const response = await api.get('/api/scripts');
    return response.data;
  },

  async startSimulation(script_id: string): Promise<Record<string, unknown>> {
    const response = await api.post('/api/simulation/start', { script_id });
    return response.data;
  },

  async nextSimulationTurn(sessionId: string): Promise<Record<string, unknown>> {
    const response = await api.post(`/api/simulation/next/${encodeURIComponent(sessionId)}`);
    return response.data;
  },

  async endSimulation(sessionId: string): Promise<Record<string, unknown>> {
    const response = await api.post(`/api/simulation/end/${encodeURIComponent(sessionId)}`);
    return response.data;
  },

  async startOutbound(payload: OutboundStartRequest): Promise<Record<string, unknown>> {
    const response = await api.post('/api/outbound/start', payload);
    return response.data;
  },

  async respondOutbound(payload: OutboundRespondRequest): Promise<Record<string, unknown>> {
    const response = await api.post('/api/outbound/respond', payload);
    return response.data;
  },

  async endOutbound(payload: OutboundEndRequest): Promise<Record<string, unknown>> {
    const response = await api.post('/api/outbound/end', payload);
    return response.data;
  },

  async getOutboundCandidates(): Promise<Record<string, unknown>> {
    const response = await api.get('/api/outbound/candidates');
    return response.data;
  },

  async getEscalationStatus(sessionId: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/api/escalation/status/${encodeURIComponent(sessionId)}`);
    return response.data;
  },

  async resolveEscalationByPath(sessionId: string): Promise<Record<string, unknown>> {
    const response = await api.post(`/api/escalation/resolve/${encodeURIComponent(sessionId)}`);
    return response.data;
  },

  async getCustomerPattern(customerId: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/api/customer-pattern/${encodeURIComponent(customerId)}`);
    return response.data;
  },

  async getCustomerSummary(customerId: string): Promise<Record<string, unknown>> {
    const response = await api.get(`/api/customer-summary/${encodeURIComponent(customerId)}`);
    return response.data;
  },

  // Stats
  async getStats(): Promise<{
    total_calls: number;
    active_calls: number;
    resolved_issues: number;
    unresolved_issues: number;
  }> {
    const response = await api.get('/stats');
    return response.data;
  },

  async resetDemoData(): Promise<{ message: string; customers: number }> {
    const response = await api.delete('/admin/reset-demo-data');
    return response.data;
  },

  // Optional endpoints used by hooks; keep resilient when backend route is absent.
  async saveOutcome(
    sessionId: string | number,
    customerId: string | number,
    resolution: 'resolved' | 'unresolved' | 'escalated'
  ): Promise<SaveOutcomeResponse> {
    try {
      const response = await api.post('/calls/outcome', {
        session_id: String(sessionId),
        customer_id: String(customerId),
        resolution,
      });
      return response.data;
    } catch {
      return { success: false, message: 'Outcome endpoint unavailable' };
    }
  },

  async resolveEscalation(sessionId: string | number): Promise<ResolveEscalationResponse> {
    try {
      const response = await api.post('/calls/resolve-escalation', {
        session_id: String(sessionId),
      });
      return response.data;
    } catch {
      return { success: false, message: 'Resolve escalation endpoint unavailable' };
    }
  },
};

export default apiService;
