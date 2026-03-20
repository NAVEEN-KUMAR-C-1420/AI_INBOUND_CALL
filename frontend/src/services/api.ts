import axios from 'axios';

const API_BASE = 'http://localhost:8020';

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
  sentiment_state?: string;
  sentiment_arc?: string[];
  language_mode?: string;
  escalation_alert?: boolean;
  trigger_phrases?: string[];
  suggestions?: Array<{
    rank: number;
    text: string;
    resolution_likelihood: number;
    tone_match: string;
  }>;
  abusive_language_detected?: boolean;
  abusive_words?: string[];
  repeat_issue_count?: number;
  repeat_caller_warning?: boolean;
  human_takeover_mode?: boolean;
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

export const apiService = {
  // Health check
  async checkHealth(): Promise<{ status: string; ollama: string }> {
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
    if (!transcript || transcript.length < 2) {
      return {
        summary: 'Call ended before sufficient conversation.',
        issue: 'other',
        sentiment: 'neutral',
        resolution: 'unresolved',
        recommended_action: 'Manual review required',
      };
    }

    const response = await fetch(`${API_BASE}/api/summary`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        transcript,
        session_id: sessionId,
        customer_phone: customerPhone,
      }),
    });

    if (!response.ok) {
      throw new Error(`Summary failed: ${response.statusText}`);
    }

    return response.json();
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
};

export default apiService;
