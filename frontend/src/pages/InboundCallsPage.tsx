import { useCallback, useEffect, useRef, useState } from 'react';
import {
  apiService,
  CallHistoryItem,
  ConversationItem,
  Customer,
  Memory,
  MessageResponse,
  Summary,
} from '../services/api';
import { IntelligencePanel } from '../components/IntelligencePanel';
import { HumanTakeoverPanel } from '../components/HumanTakeoverPanel';
import { useSpeechRecognition, useTextToSpeech } from '../hooks/useSpeech';

type CallState = 'idle' | 'ringing' | 'active' | 'ended';

interface TranscriptItem {
  speaker: 'customer' | 'ai';
  message: string;
  intent?: string;
  sentiment?: string;
}

function InboundCallsPage() {
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
  } | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [showSummary, setShowSummary] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [clientName, setClientName] = useState('TeleCorp');
  const [isProcessing, setIsProcessing] = useState(false);
  const [languageMode, setLanguageMode] = useState('en');
  const [speechLanguage, setSpeechLanguage] = useState('en-US');
  const [escalationAlert, setEscalationAlert] = useState(false);
  const [triggerPhrases, setTriggerPhrases] = useState<string[]>([]);
  const [aiSuggestions, setAiSuggestions] = useState<Array<{ suggestion: string; tone: string }>>([]);
  const [customerSentimentArc, setCustomerSentimentArc] = useState<string[]>([]);
  const [isHumanTakeover, setIsHumanTakeover] = useState(false);
  const [dialPhone, setDialPhone] = useState('');
  const [dialName, setDialName] = useState('');
  const [isDialing, setIsDialing] = useState(false);

  const buildFallbackSuggestions = useCallback((aiText: string, sentiment: string) => {
    const base = (aiText || '').trim();
    const next: Array<{ suggestion: string; tone: string }> = [];

    if (base) {
      next.push({ suggestion: `You can say: ${base}`, tone: 'manager-script' });
    }
    if (sentiment.toLowerCase() === 'angry' || sentiment.toLowerCase() === 'frustrated') {
      next.push({
        suggestion: 'You can say: I understand your frustration and I will stay on this until we resolve it for you.',
        tone: 'de-escalation-script',
      });
    }
    next.push({
      suggestion: 'You can say: I have your account context already. Let me confirm the exact fix and next step now.',
      tone: 'ownership-script',
    });

    return next.slice(0, 3);
  }, []);

  const playEscalationBeep = useCallback(() => {
    try {
      const Ctx = (window.AudioContext || (window as any).webkitAudioContext) as typeof AudioContext | undefined;
      if (!Ctx) return;
      const ctx = new Ctx();
      const now = ctx.currentTime;

      const makeBeep = (at: number) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(880, at);
        gain.gain.setValueAtTime(0.0001, at);
        gain.gain.exponentialRampToValueAtTime(0.18, at + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.0001, at + 0.22);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(at);
        osc.stop(at + 0.24);
      };

      makeBeep(now);
      makeBeep(now + 0.28);
      setTimeout(() => ctx.close(), 900);
    } catch (e) {
      console.warn('Escalation beep failed:', e);
    }
  }, []);

  const transcriptRef = useRef<HTMLDivElement>(null);
  const lastProcessedRef = useRef<string>('');

  const {
    transcript: spokenText,
    interimTranscript,
    isListening,
    isSupported: speechRecognitionSupported,
    startListening,
    stopListening,
    resetTranscript,
  } = useSpeechRecognition(speechLanguage);

  const { speak, stop: stopSpeaking, isSpeaking, isSupported: ttsSupported } = useTextToSpeech();

  useEffect(() => {
    const checkConnection = async () => {
      try {
        const health = await apiService.checkHealth();
        setIsConnected(health.ollama === 'connected');
        if (health.client_name) {
          setClientName(health.client_name);
        }
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
        });
        setCustomerSentimentArc(prev => [...prev, response.sentiment || 'neutral']);

        const escalationRaised = Boolean(
          response.escalation_alert ||
          (response.sentiment?.toLowerCase() === 'angry' && response.urgency?.toLowerCase() === 'high')
        );
        setEscalationAlert(escalationRaised);
        setTriggerPhrases(response.trigger_phrases || []);
        setLanguageMode(response.language_mode || 'en');
        const nextSuggestions = response.suggestions && response.suggestions.length > 0
          ? response.suggestions
          : buildFallbackSuggestions(response.ai_response || '', response.sentiment || 'neutral');
        setAiSuggestions(nextSuggestions);

        if (escalationRaised) {
          setIsHumanTakeover(true);
          stopListening();
          playEscalationBeep();
        }

        const aiText = (response.ai_response || '').trim();
        const safeAiText = aiText || 'I have received your query and I am checking the best resolution now.';

        setTranscript(prev => [
          ...prev,
          {
            speaker: 'ai',
            message: safeAiText,
            intent: response.intent,
            sentiment: response.sentiment,
          },
        ]);

        if (ttsSupported) {
          speak(safeAiText);
        }
      } catch (error) {
        console.error('Failed to send message:', error);
      } finally {
        setIsProcessing(false);
        resetTranscript();
      }
    },
        [buildFallbackSuggestions, currentCallId, isProcessing, playEscalationBeep, resetTranscript, speak, stopListening, ttsSupported]
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

  const simulateIncomingCall = () => {
    if (!selectedCustomer) {
      return;
    }

    setCallState('ringing');
    setSelectedHistoryCallId(null);
    setTranscript([]);
    setSummary(null);
    setShowSummary(false);
    setEscalationAlert(false);
    setTriggerPhrases([]);
    setAiSuggestions([]);
    setCustomerSentimentArc([]);
    setIsHumanTakeover(false);
  };

  const normalizePhone = (value: string) => value.replace(/[\s()-]/g, '').trim();

  const startActiveCall = useCallback(async (customer: Customer) => {
    const call = await apiService.startCall(customer.id);
    setCurrentCallId(call.id);
    setCallState('active');
    setEscalationAlert(false);
    setTriggerPhrases([]);
    setAiSuggestions([]);
    setCustomerSentimentArc([]);
    setIsHumanTakeover(false);

    const firstName = customer.name.split(' ')[0] || customer.name;
    const greeting = `Hello ${firstName}, this is Sarah from ${clientName} customer service. How may I assist you today?`;
    setTranscript([{ speaker: 'ai', message: greeting }]);

    if (ttsSupported) {
      speak(greeting);
    }
  }, [clientName, speak, ttsSupported]);

  const callByPhone = useCallback(async () => {
    const normalizedPhone = normalizePhone(dialPhone);
    if (!normalizedPhone) {
      window.alert('Please enter phone number.');
      return;
    }

    setIsDialing(true);
    try {
      const existing = customers.find(c => normalizePhone(c.phone) === normalizedPhone);
      let targetCustomer = existing || null;

      if (!targetCustomer) {
        if (!dialName.trim()) {
          window.alert('Name is required for a new phone number.');
          return;
        }
        targetCustomer = await apiService.createCustomer({
          name: dialName.trim(),
          phone: dialPhone.trim(),
          plan: 'Basic',
        });
      }

      const refreshedCustomers = await apiService.getCustomers();
      setCustomers(refreshedCustomers);

      const selected = refreshedCustomers.find(c => c.id === targetCustomer.id) || targetCustomer;
      setSelectedCustomer(selected);
      setSelectedHistoryCallId(null);
      setSummary(null);
      setShowSummary(false);
      setTranscript([]);

      await startActiveCall(selected);
    } catch (error) {
      console.error('Call by phone failed:', error);
      window.alert('Unable to start call. Please try again.');
    } finally {
      setIsDialing(false);
    }
  }, [customers, dialName, dialPhone, startActiveCall]);

  const acceptCall = async () => {
    if (!selectedCustomer) {
      return;
    }

    try {
      await startActiveCall(selectedCustomer);
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
        const [memory, calls, freshCustomers] = await Promise.all([
          apiService.getCustomerMemory(selectedCustomer.id),
          apiService.getCustomerCalls(selectedCustomer.id),
          apiService.getCustomers(),
        ]);
        setCustomers(freshCustomers);
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
    setIsHumanTakeover(false);
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
      setCustomerSentimentArc(
        mappedTranscript
          .filter(item => item.speaker === 'customer')
          .map(item => item.sentiment || 'neutral')
      );
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
    setEscalationAlert(false);
    setTriggerPhrases([]);
    setAiSuggestions([]);
    setCustomerSentimentArc([]);
    setIsHumanTakeover(false);
    setLanguageMode('en');
    setDialName('');
    setDialPhone('');
    setCallKey(prev => prev + 1);
  };

  const handleEscalateToHuman = () => {
    setEscalationAlert(true);
    setIsHumanTakeover(true);
    stopListening();
    playEscalationBeep();
  };

  const handleToggleHumanTakeover = () => {
    setIsHumanTakeover(prev => {
      const next = !prev;
      if (next) {
        stopListening();
      }
      return next;
    });
  };

  const handleSendHumanText = (text: string) => {
    const clean = text.trim();
    if (!clean) return;
    setTranscript(prev => [
      ...prev,
      {
        speaker: 'ai',
        message: `[Human Agent] ${clean}`,
        intent: currentAnalysis?.intent,
        sentiment: currentAnalysis?.sentiment,
      },
    ]);
    if (ttsSupported) {
      speak(clean);
    }
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

              <div className="direct-call-box">
                <h4>Call By Phone</h4>
                <input
                  className="direct-call-input"
                  type="tel"
                  placeholder="Phone number"
                  value={dialPhone}
                  onChange={(e) => setDialPhone(e.target.value)}
                />
                <input
                  className="direct-call-input"
                  type="text"
                  placeholder="Name (required for new number)"
                  value={dialName}
                  onChange={(e) => setDialName(e.target.value)}
                />
                <button className="btn btn-call" onClick={callByPhone} disabled={!isConnected || isDialing}>
                  {isDialing ? 'Connecting...' : '📲 Call AI Agent'}
                </button>
              </div>
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

                  <select
                    value={speechLanguage}
                    onChange={(e) => setSpeechLanguage(e.target.value)}
                    style={{
                      background: 'rgba(255,255,255,0.08)',
                      color: '#fff',
                      border: '1px solid rgba(255,255,255,0.2)',
                      borderRadius: 8,
                      padding: '8px 10px',
                      marginLeft: 8,
                    }}
                    title="Speech input language"
                  >
                    <option value="en-US">English</option>
                    <option value="ta-IN">Tamil</option>
                    <option value="en-IN">Tanglish (Indian English)</option>
                  </select>

                  <button className="btn btn-end" onClick={endCall}>
                    📵 End Call
                  </button>
                </div>
              )}

              {callState === 'active' && (
                <HumanTakeoverPanel
                  isEnabled={isHumanTakeover}
                  onToggleTakeover={handleToggleHumanTakeover}
                  onSendText={handleSendHumanText}
                  aiSuggestions={aiSuggestions}
                />
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
            sentimentState={currentAnalysis?.sentiment || 'neutral'}
            sentimentArc={customerSentimentArc}
            languageMode={languageMode}
            escalationAlert={escalationAlert}
            triggerPhrases={triggerPhrases}
            suggestions={[]}
            customer={selectedCustomer}
            isCallActive={callState === 'active'}
            aiResponse={
              aiSuggestions[0]?.suggestion
              || [...transcript].reverse().find(item => item.speaker === 'ai')?.message
              || ''
            }
            hasCustomerSpoken={transcript.some(item => item.speaker === 'customer')}
            previousCallCount={customerCalls.length}
            lastIssue={customerMemory[0]?.issue}
            isRepeatIssue={customerCalls.length >= 3 && customerMemory[0]?.status !== 'resolved'}
            onEscalate={handleEscalateToHuman}
            onEnableHumanTakeover={handleEscalateToHuman}
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

export default InboundCallsPage;
