import { useCallback, useEffect, useRef, useState } from 'react';
import {
  apiService,
  CallHistoryItem,
  ConversationItem,
  Customer,
  Memory,
  MessageResponse,
  Summary,
} from './services/api';
import { IntelligencePanel } from './components/IntelligencePanel';
import { HumanTakeoverPanel } from './components/HumanTakeoverPanel';
import { useSpeechRecognition, useTextToSpeech } from './hooks/useSpeech';

type CallState = 'idle' | 'ringing' | 'active' | 'ended';

interface TranscriptItem {
  speaker: 'customer' | 'ai';
  message: string;
  intent?: string;
  sentiment?: string;
}

function App() {
  const WS_REALTIME_URL = 'ws://localhost:8020/ws/realtime/assist';
  const [callKey, setCallKey] = useState(0);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [customerMemory, setCustomerMemory] = useState<Memory[]>([]);
  const [customerCalls, setCustomerCalls] = useState<CallHistoryItem[]>([]);
  const [selectedHistoryCallId, setSelectedHistoryCallId] = useState<number | null>(null);
  const [callState, setCallState] = useState<CallState>('idle');
  const [currentCallId, setCurrentCallId] = useState<number | null>(null);
  const [transcript, setTranscript] = useState<TranscriptItem[]>([]);
  const [currentAnalysis, setCurrentAnalysis] = useState<{
    intent: string;
    sentiment: string;
    urgency: string;
    sentimentState?: string;
    sentimentArc?: string[];
    languageMode?: string;
    escalationAlert?: boolean;
    triggerPhrases?: string[];
    suggestions?: Array<{
      rank: number;
      text: string;
      resolution_likelihood: number;
      tone_match: string;
    }>;
    abusiveLanguageDetected?: boolean;
    abusiveWords?: string[];
    repeatIssueCount?: number;
    repeatCallerWarning?: boolean;
  } | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [showSummary, setShowSummary] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [humanTakeoverMode, setHumanTakeoverMode] = useState(false);
  const [abusiveLanguageDetected, setAbusiveLanguageDetected] = useState(false);
  const [abusiveWords, setAbusiveWords] = useState<string[]>([]);
  const [repeatIssueCount, setRepeatIssueCount] = useState(0);
  const [repeatCallerWarning, setRepeatCallerWarning] = useState(false);

  const transcriptRef = useRef<HTMLDivElement>(null);
  const lastProcessedRef = useRef<string>('');
  const wsRef = useRef<WebSocket | null>(null);
  const realtimeSessionRef = useRef<string>(`rt-${Date.now()}`);
  const lastInterimSentRef = useRef<string>('');

  const {
    transcript: spokenText,
    interimTranscript,
    isListening,
    isSupported: speechRecognitionSupported,
    startListening,
    stopListening,
    resetTranscript,
  } = useSpeechRecognition();

  const { speak, stop: stopSpeaking, isSpeaking, isSupported: ttsSupported } = useTextToSpeech();

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const health = await apiService.checkHealth();
        setIsConnected(health.ollama === 'connected');
      } catch {
        setIsConnected(false);
      }
    };

    checkConnection();
    const interval = setInterval(checkConnection, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const loadCustomers = async () => {
      try {
        const data = await apiService.getCustomers();
        setCustomers(data);
      } catch (error) {
        console.error('Failed to load customers:', error);
      }
    };

    loadCustomers();
  }, []);

  useEffect(() => {
    if (!selectedCustomer) {
      return;
    }

    const loadContext = async () => {
      try {
        const [memory, calls] = await Promise.all([
          apiService.getCustomerMemory(selectedCustomer.id),
          apiService.getCustomerCalls(selectedCustomer.id),
        ]);
        setCustomerMemory(memory);
        setCustomerCalls(calls);
      } catch (error) {
        console.error('Failed to load customer context:', error);
      }
    };

    loadContext();
  }, [selectedCustomer]);

  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [transcript]);

  useEffect(() => {
    if (callState !== 'active') {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      return;
    }

    const ws = new WebSocket(WS_REALTIME_URL);
    wsRef.current = ws;

    ws.onmessage = event => {
      try {
        const data = JSON.parse(event.data);
        if (data?.error) {
          return;
        }
        setCurrentAnalysis(prev => ({
          intent: data.intent || prev?.intent || 'account_query',
          sentiment: data.sentiment || prev?.sentiment || 'neutral',
          urgency: data.urgency || prev?.urgency || 'low',
          sentimentState: data.sentiment_state || prev?.sentimentState,
          sentimentArc: data.sentiment_arc || prev?.sentimentArc || [],
          languageMode: data.language_mode || prev?.languageMode || 'english',
          escalationAlert: Boolean(data.escalation_alert),
          triggerPhrases: data.trigger_phrases || prev?.triggerPhrases || [],
          suggestions: data.suggestions || prev?.suggestions || [],
        }));
      } catch {
        // Ignore parse errors for non-JSON websocket messages.
      }
    };

    return () => {
      ws.close();
    };
  }, [callState]);

  const processMessage = useCallback(
    async (message: string) => {
      if (!currentCallId || !message.trim() || isProcessing) {
        return;
      }

      setIsProcessing(true);
      lastProcessedRef.current = message;
      setTranscript(prev => [...prev, { speaker: 'customer', message }]);

      try {
        const response: MessageResponse = await apiService.sendMessage(currentCallId, message);

        setCurrentAnalysis({
          intent: response.intent,
          sentiment: response.sentiment,
          urgency: response.urgency,
          sentimentState: response.sentiment_state,
          sentimentArc: response.sentiment_arc,
          languageMode: response.language_mode,
          escalationAlert: response.escalation_alert,
          triggerPhrases: response.trigger_phrases,
          suggestions: response.suggestions,
          abusiveLanguageDetected: response.abusive_language_detected,
          abusiveWords: response.abusive_words,
          repeatIssueCount: response.repeat_issue_count,
          repeatCallerWarning: response.repeat_caller_warning,
        });

        // Update state for UI
        setAbusiveLanguageDetected(response.abusive_language_detected || false);
        setAbusiveWords(response.abusive_words || []);
        setRepeatIssueCount(response.repeat_issue_count || 0);
        setRepeatCallerWarning(response.repeat_caller_warning || false);

        setTranscript(prev => [
          ...prev,
          {
            speaker: 'ai',
            message: response.ai_response,
            intent: response.intent,
            sentiment: response.sentiment,
          },
        ]);

        if (ttsSupported) {
          speak(response.ai_response);
        }
      } catch (error) {
        console.error('Failed to send message:', error);
      } finally {
        setIsProcessing(false);
        resetTranscript();
      }
    },
    [currentCallId, isProcessing, resetTranscript, speak, ttsSupported]
  );

  useEffect(() => {
    const trimmed = spokenText.trim();
    if (
      trimmed &&
      trimmed !== lastProcessedRef.current &&
      !isListening &&
      callState === 'active' &&
      !isProcessing &&
      !isSpeaking
    ) {
      processMessage(trimmed);
    }
  }, [spokenText, isListening, callState, isProcessing, isSpeaking, processMessage]);

  useEffect(() => {
    const chunk = interimTranscript.trim();
    if (
      callState !== 'active' ||
      !isListening ||
      !chunk ||
      chunk.length < 10 ||
      chunk === lastInterimSentRef.current ||
      !wsRef.current ||
      wsRef.current.readyState !== WebSocket.OPEN
    ) {
      return;
    }

    const payload = {
      session_id: realtimeSessionRef.current,
      chunk,
      role: 'customer',
      call_type: 'inbound',
      customer_phone: selectedCustomer?.phone,
      customer_name: selectedCustomer?.name,
    };

    wsRef.current.send(JSON.stringify(payload));
    lastInterimSentRef.current = chunk;
  }, [interimTranscript, callState, isListening, selectedCustomer]);

  const simulateIncomingCall = () => {
    if (!selectedCustomer) {
      return;
    }

    setCallState('ringing');
    setSelectedHistoryCallId(null);
    setTranscript([]);
    setSummary(null);
    setShowSummary(false);
  };

  const acceptCall = async () => {
    if (!selectedCustomer) {
      return;
    }

    try {
      const call = await apiService.startCall(selectedCustomer.id);
      setCurrentCallId(call.id);
      setCallState('active');

      const firstName = selectedCustomer.name.split(' ')[0] || selectedCustomer.name;
      const greeting = `Hello ${firstName}, this is Sarah from TeleCorp customer service. How may I assist you today?`;
      setTranscript([{ speaker: 'ai', message: greeting }]);

      if (ttsSupported) {
        speak(greeting);
      }
    } catch (error) {
      console.error('Failed to start call:', error);
    }
  };

  const rejectCall = () => setCallState('idle');

  const endCall = async () => {
    if (!currentCallId) {
      return;
    }

    const endedCallId = currentCallId;
    stopListening();
    stopSpeaking();
    setCallState('ended');

    try {
      const transcriptForSummary = transcript.map(item => ({
        role: item.speaker === 'customer' ? 'user' : 'assistant',
        content: item.message,
      }));

      const [summaryResult] = await Promise.all([
        apiService.generateSummary(
          transcriptForSummary,
          `session-${callKey}-${Date.now()}`,
          selectedCustomer?.phone
        ),
        apiService.endCall(currentCallId),
      ]);

      setSummary({
        summary: summaryResult.summary,
        issue: summaryResult.issue,
        sentiment: summaryResult.sentiment,
        resolved: summaryResult.resolution === 'resolved',
        action: summaryResult.recommended_action,
        compliance: 'ok',
        decision: summaryResult.resolution === 'resolved' ? 'resolve' : 'follow_up',
      });
      setShowSummary(true);

      if (selectedCustomer) {
        const [memory, calls] = await Promise.all([
          apiService.getCustomerMemory(selectedCustomer.id),
          apiService.getCustomerCalls(selectedCustomer.id),
        ]);
        setCustomerMemory(memory);
        setCustomerCalls(calls);
        setSelectedHistoryCallId(endedCallId);
      }
    } catch (error) {
      console.error('Failed to end call:', error);
      setSummary({
        summary: 'Unable to generate summary.',
        issue: 'other',
        sentiment: 'neutral',
        resolved: false,
        action: 'Manual review required',
        compliance: 'ok',
        decision: 'follow_up',
      });
      setShowSummary(true);
    }

    setCurrentCallId(null);
  };

  const loadPreviousCall = async (callId: number) => {
    try {
      const [historyTranscript, historySummary] = await Promise.all([
        apiService.getTranscript(callId),
        apiService.getSummary(callId).catch(() => null),
      ]);

      const mappedTranscript: TranscriptItem[] = historyTranscript.map((item: ConversationItem) => ({
        speaker: item.speaker === 'customer' ? 'customer' : 'ai',
        message: item.message,
        intent: item.intent,
        sentiment: item.sentiment,
      }));

      setTranscript(mappedTranscript);
      setSummary(historySummary);
      setShowSummary(Boolean(historySummary));
      setSelectedHistoryCallId(callId);
      setCallState('ended');
      setCurrentCallId(null);
    } catch (error) {
      console.error('Failed to load previous call:', error);
    }
  };

  const resetOldRecords = async () => {
    const confirmed = window.confirm('Delete all old customer call records and reset demo data?');
    if (!confirmed) {
      return;
    }

    try {
      await apiService.resetDemoData();
      const freshCustomers = await apiService.getCustomers();
      setCustomers(freshCustomers);
      resetToIdle();
    } catch (error) {
      console.error('Failed to reset old records:', error);
    }
  };

  const resetToIdle = () => {
    setShowSummary(false);
    setSummary(null);
    setCallState('idle');
    setCurrentAnalysis(null);
    setTranscript([]);
    setCurrentCallId(null);
    setSelectedCustomer(null);
    setCustomerCalls([]);
    setCustomerMemory([]);
    setSelectedHistoryCallId(null);
    setHumanTakeoverMode(false);
    setAbusiveLanguageDetected(false);
    setAbusiveWords([]);
    setRepeatIssueCount(0);
    setRepeatCallerWarning(false);
    setCallKey(prev => prev + 1);
  };

  const toggleMic = () => {
    if (isListening) {
      stopListening();
    } else {
      startListening();
    }
  };

  const getSentimentClass = (sentiment?: string) => {
    const s = sentiment?.toLowerCase() || '';
    if (s.includes('positive')) return 'sentiment-positive';
    if (s.includes('negative')) return 'sentiment-negative';
    if (s.includes('angry')) return 'sentiment-angry';
    return 'sentiment-neutral';
  };

  const handleEscalate = async () => {
    try {
      const response = await fetch('http://localhost:8020/api/escalate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: realtimeSessionRef.current,
          reason: abusiveLanguageDetected ? 'abusive_language' : 'escalation_alert',
          escalation_phone: '1-800-TELECORP',
        }),
      });
      const data = await response.json();
      console.log('Escalation initiated:', data);
      alert(`Escalating to: ${data.escalation_phone}\nReference: ${data.reference_id}`);
    } catch (error) {
      console.error('Escalation error:', error);
    }
  };

  const handleEnableHumanTakeover = async () => {
    try {
      const response = await fetch('http://localhost:8020/api/human-takeover/enable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: realtimeSessionRef.current,
        }),
      });
      const data = await response.json();
      setHumanTakeoverMode(true);
      console.log('Human takeover enabled:', data);
    } catch (error) {
      console.error('Human takeover error:', error);
    }
  };

  const handleSendHumanText = async (text: string) => {
    try {
      const response = await fetch('http://localhost:8020/api/human-takeover/send-text', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: realtimeSessionRef.current,
          text: text,
        }),
      });
      const data = await response.json();
      // Speak the text for the customer
      if (ttsSupported) {
        speak(text);
      }
      console.log('Text sent:', data);
    } catch (error) {
      console.error('Send text error:', error);
    }
  };

  const handleDisableHumanTakeover = async () => {
    try {
      const response = await fetch('http://localhost:8020/api/human-takeover/disable', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: realtimeSessionRef.current,
        }),
      });
      const data = await response.json();
      setHumanTakeoverMode(false);
      console.log('Human takeover disabled:', data);
    } catch (error) {
      console.error('Disable takeover error:', error);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Telecom AI Call System</h1>
        <p>Intelligent Customer Service with Memory and Decision Making</p>
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}></span>
          <span className="status-text">
            {isConnected ? 'Ollama Connected' : 'Ollama Disconnected - Start Ollama server'}
          </span>
        </div>
      </header>

      <main className="main-content">
        <div className="panel">
          <h2 className="panel-title">📋 Customers</h2>
          <button className="btn btn-reset" onClick={resetOldRecords}>
            🧹 Reset Old Records
          </button>

          <div className="customer-list">
            {customers.map(customer => (
              <div
                key={customer.id}
                className={`customer-card ${selectedCustomer?.id === customer.id ? 'selected' : ''}`}
                onClick={() => setSelectedCustomer(customer)}
              >
                <div className="customer-name">{customer.name}</div>
                <div className="customer-phone">{customer.phone}</div>
                <span className="customer-plan">{customer.plan}</span>
              </div>
            ))}
          </div>

          {selectedCustomer && customerMemory.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <h3 className="panel-title">🧠 Customer History</h3>
              {customerMemory.slice(0, 3).map((mem, idx) => (
                <div key={idx} className={`memory-item ${mem.status}`}>
                  <div className="memory-issue">{mem.issue}</div>
                  <div className="memory-status">
                    Status: {mem.status} | Sentiment: {mem.sentiment || 'N/A'}
                  </div>
                </div>
              ))}
            </div>
          )}

          {selectedCustomer && (
            <div style={{ marginTop: 20 }}>
              <h3 className="panel-title">🗂️ Previous Calls</h3>
              {customerCalls.length === 0 && <div className="history-empty">No previous calls for this customer.</div>}
              {customerCalls.map(call => (
                <button
                  key={call.id}
                  className={`history-card ${selectedHistoryCallId === call.id ? 'selected' : ''}`}
                  onClick={() => loadPreviousCall(call.id)}
                >
                  <div className="history-header">
                    <span>Call #{call.id}</span>
                    <span>{new Date(call.start_time).toLocaleString()}</span>
                  </div>
                  <div className="history-summary">
                    {call.summary || call.issue || 'Summary unavailable. Click to open transcript.'}
                  </div>
                  <div className="history-meta">
                    {call.status} {typeof call.resolved === 'boolean' ? `| ${call.resolved ? 'resolved' : 'unresolved'}` : ''}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div key={callKey} className="panel call-panel">
          <h2 className="panel-title">📞 Call Center</h2>

          {callState === 'idle' && (
            <div className="call-status">
              <div className="call-icon">📱</div>
              <p>Select a customer and simulate an incoming call</p>
              <button className="btn btn-call" onClick={simulateIncomingCall} disabled={!selectedCustomer || !isConnected}>
                📞 Simulate Incoming Call
              </button>
            </div>
          )}

          {callState === 'ringing' && (
            <div className="call-status ringing">
              <div className="call-icon">📞</div>
              <h3>Incoming Call</h3>
              <p>{selectedCustomer?.name}</p>
              <p style={{ color: 'rgba(255,255,255,0.6)' }}>{selectedCustomer?.phone}</p>
              <div className="call-buttons">
                <button className="btn btn-accept" onClick={acceptCall}>
                  ✓ Accept
                </button>
                <button className="btn btn-reject" onClick={rejectCall}>
                  ✕ Reject
                </button>
              </div>
            </div>
          )}

          {(callState === 'active' || callState === 'ended') && (
            <>
              <div className="transcript" ref={transcriptRef}>
                {transcript.map((item, idx) => (
                  <div key={idx} className={`transcript-message ${item.speaker}`}>
                    <span className="message-label">{item.speaker === 'customer' ? 'Customer' : 'AI Sarah'}</span>
                    <div className="message-bubble">{item.message}</div>
                  </div>
                ))}

                {interimTranscript && (
                  <div className="transcript-message customer">
                    <span className="message-label">You (speaking...)</span>
                    <div className="message-bubble" style={{ opacity: 0.6 }}>
                      {interimTranscript}
                    </div>
                  </div>
                )}

                {isProcessing && (
                  <div className="loading">
                    <div className="spinner"></div>
                    <span>AI is thinking...</span>
                  </div>
                )}

                {isSpeaking && (
                  <div className="loading">
                    <span>🔊 AI is speaking...</span>
                  </div>
                )}
              </div>

              {callState === 'active' && (
                <div className="mic-control">
                  <button
                    className={`mic-button ${isListening ? 'listening' : ''}`}
                    onClick={toggleMic}
                    disabled={!speechRecognitionSupported || isProcessing || isSpeaking}
                  >
                    {isListening ? '🎙️' : '🎤'}
                  </button>
                  <div className="mic-status">
                    {!speechRecognitionSupported && 'Speech recognition not supported'}
                    {speechRecognitionSupported && isListening && (
                      <div className="listening-indicator">
                        <span className="listening-dot"></span>
                        <span className="listening-dot"></span>
                        <span className="listening-dot"></span>
                        <span style={{ marginLeft: 8 }}>Listening...</span>
                      </div>
                    )}
                    {speechRecognitionSupported && !isListening && 'Click to speak'}
                  </div>

                  <button className="btn btn-end" onClick={endCall}>
                    📵 End Call
                  </button>
                </div>
              )}

              {callState === 'ended' && (
                <div style={{ textAlign: 'center', padding: 20 }}>
                  <p>Call ended</p>
                  <button className="btn btn-call" onClick={resetToIdle} style={{ marginTop: 15 }}>
                    Start New Call
                  </button>
                </div>
              )}
            </>
          )}
        </div>

        <div className="panel">
          <h2 className="panel-title">🧠 Real-Time Intelligence</h2>
          <IntelligencePanel
            intent={currentAnalysis?.intent || 'account_query'}
            sentiment={currentAnalysis?.sentiment || 'neutral'}
            urgency={currentAnalysis?.urgency || 'low'}
            sentimentState={currentAnalysis?.sentimentState || 'neutral'}
            sentimentArc={currentAnalysis?.sentimentArc || []}
            languageMode={currentAnalysis?.languageMode || 'english'}
            escalationAlert={Boolean(currentAnalysis?.escalationAlert)}
            triggerPhrases={currentAnalysis?.triggerPhrases || []}
            suggestions={currentAnalysis?.suggestions || []}
            customer={selectedCustomer}
            isCallActive={callState === 'active'}
            aiResponse={[...transcript].reverse().find(item => item.speaker === 'ai')?.message || ''}
            hasCustomerSpoken={transcript.some(item => item.speaker === 'customer')}
            previousCallCount={customerCalls.length}
            lastIssue={customerMemory[0]?.issue}
            isRepeatIssue={customerCalls.length >= 3 && customerMemory[0]?.status !== 'resolved'}
            abusiveLanguageDetected={abusiveLanguageDetected}
            abusiveWords={abusiveWords}
            repeatIssueCount={repeatIssueCount}
            repeatCallerWarning={repeatCallerWarning}
            onEscalate={handleEscalate}
            onEnableHumanTakeover={handleEnableHumanTakeover}
          />

          <div style={{ marginTop: 16 }}>
            <div className="intelligence-card">
              <div className="intelligence-label">Speech Recognition</div>
              <div className={`intelligence-value ${speechRecognitionSupported ? 'sentiment-positive' : 'sentiment-negative'}`}>
                {speechRecognitionSupported ? 'Available' : 'Not Supported'}
              </div>
            </div>
            <div className="intelligence-card">
              <div className="intelligence-label">Text-to-Speech</div>
              <div className={`intelligence-value ${ttsSupported ? 'sentiment-positive' : 'sentiment-negative'}`}>
                {ttsSupported ? 'Available' : 'Not Supported'}
              </div>
            </div>
          </div>

          <HumanTakeoverPanel
            onSendText={handleSendHumanText}
            aiSuggestions={[
              { suggestion: "Let me look into that for you right away.", tone: "empathetic" },
              { suggestion: "I completely understand your frustration. Let's resolve this.", tone: "understanding" },
              { suggestion: "I'd like to escalate this to my manager for you.", tone: "professional" },
            ]}
            isEnabled={humanTakeoverMode}
          />

          {humanTakeoverMode && (
            <button
              onClick={handleDisableHumanTakeover}
              style={{
                marginTop: 10,
                padding: '10px 16px',
                background: '#6B7280',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                width: '100%',
              }}
            >
              ✓ Return to AI-Assisted Mode
            </button>
          )}
        </div>
      </main>

      <div className={`summary-panel ${showSummary ? 'open' : ''}`}>
        <button className="summary-close" onClick={() => setShowSummary(false)}>
          ×
        </button>
        <h2 className="panel-title">📊 Call Summary</h2>

        {summary && (
          <>
            <div className="summary-section">
              <div className="summary-label">Summary</div>
              <div className="summary-value">{summary.summary}</div>
            </div>

            <div className="summary-section">
              <div className="summary-label">Issue</div>
              <div className="summary-value">{summary.issue}</div>
            </div>

            <div className="summary-section">
              <div className="summary-label">Sentiment</div>
              <div className="summary-value">
                <span className={`summary-badge ${getSentimentClass(summary.sentiment)}`}>{summary.sentiment}</span>
              </div>
            </div>

            <div className="summary-section">
              <div className="summary-label">Resolution Status</div>
              <div className="summary-value">
                <span className={`summary-badge ${summary.resolved ? 'badge-resolved' : 'badge-unresolved'}`}>
                  {summary.resolved ? 'Resolved' : 'Unresolved'}
                </span>
              </div>
            </div>

            <div className="summary-section">
              <div className="summary-label">Recommended Action</div>
              <div className="summary-value">{summary.action}</div>
            </div>

            <div className="summary-section">
              <div className="summary-label">Decision</div>
              <div className="summary-value">
                <span className={`summary-badge ${summary.decision === 'escalate' ? 'badge-escalate' : 'badge-resolved'}`}>
                  {summary.decision}
                </span>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default App;
