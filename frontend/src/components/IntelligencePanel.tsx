import { Customer } from '../services/api';

interface Props {
  intent: string;
  sentiment: string;
  urgency: string;
  sentimentState: string;
  sentimentArc: string[];
  languageMode: string;
  escalationAlert: boolean;
  triggerPhrases: string[];
  suggestions: Array<{
    rank: number;
    text: string;
    resolution_likelihood: number;
    tone_match: string;
  }>;
  customer: Customer | null;
  isCallActive: boolean;
  aiResponse: string;
  hasCustomerSpoken: boolean;
  previousCallCount: number;
  lastIssue?: string;
  isRepeatIssue: boolean;
  abusiveLanguageDetected?: boolean;
  abusiveWords?: string[];
  repeatIssueCount?: number;
  repeatCallerWarning?: boolean;
  onEscalate?: () => void;
  onEnableHumanTakeover?: () => void;
}

export function IntelligencePanel({
  intent,
  sentiment,
  urgency,
  sentimentState,
  sentimentArc,
  languageMode,
  escalationAlert,
  triggerPhrases,
  suggestions,
  customer,
  isCallActive,
  aiResponse,
  hasCustomerSpoken,
  previousCallCount,
  lastIssue,
  isRepeatIssue,
  abusiveLanguageDetected,
  abusiveWords,
  repeatIssueCount,
  repeatCallerWarning,
  onEscalate,
  onEnableHumanTakeover,
}: Props) {
  const sentimentColor: Record<string, string> = {
    positive: '#06D6A0',
    neutral: '#FFB703',
    frustrated: '#F97316',
    angry: '#EF4444',
    negative: '#EF4444',
  };

  const urgencyColor: Record<string, string> = {
    high: '#EF4444',
    medium: '#FFB703',
    low: '#06D6A0',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {customer && (
        <div
          style={{
            background: 'rgba(255,255,255,0.05)',
            borderRadius: 8,
            padding: 12,
            borderLeft: `3px solid ${isRepeatIssue ? '#EF4444' : '#06D6A0'}`,
          }}
        >
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Customer history
          </div>
          <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 4 }}>{customer.name}</div>
          <div style={{ fontSize: 12, color: '#94A3B8', marginBottom: 8 }}>
            {customer.plan} • {previousCallCount} previous calls
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
            <span style={{ color: '#94A3B8' }}>Last issue</span>
            <span style={{ color: '#E2E8F0' }}>{lastIssue || 'N/A'}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
            <span style={{ color: '#94A3B8' }}>Call status</span>
            <span style={{ color: isCallActive ? '#06D6A0' : '#94A3B8', fontWeight: 500 }}>
              {isCallActive ? 'Connected' : 'Idle'}
            </span>
          </div>
          {isRepeatIssue && (
            <div
              style={{
                marginTop: 8,
                padding: '6px 10px',
                background: 'rgba(239,68,68,0.15)',
                border: '1px solid rgba(239,68,68,0.3)',
                borderRadius: 6,
                fontSize: 11,
                color: '#FCA5A5',
              }}
            >
              Repeat issue detected. Escalate if unresolved today.
            </div>
          )}
        </div>
      )}

      <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 12 }}>
        <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Current intent
        </div>
        <div style={{ fontSize: 15, fontWeight: 500, color: '#E2E8F0' }}>
          {hasCustomerSpoken ? intent.replace(/_/g, ' ') : 'Waiting for customer...'}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 12 }}>
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Sentiment
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: sentimentColor[sentiment] || '#94A3B8' }}>
            {hasCustomerSpoken ? sentiment : 'N/A'}
          </div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 12 }}>
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Urgency
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: urgencyColor[urgency] || '#94A3B8' }}>
            {hasCustomerSpoken ? urgency : 'N/A'}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 12 }}>
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Sentiment State
          </div>
          <div style={{ fontSize: 13, fontWeight: 500, color: '#E2E8F0' }}>
            {sentimentState.replace(/_/g, ' ')}
          </div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 12 }}>
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Language Mode
          </div>
          <div style={{ fontSize: 13, fontWeight: 500, color: '#E2E8F0' }}>
            {languageMode}
          </div>
        </div>
      </div>

      <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 12 }}>
        <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          Sentiment Arc
        </div>
        <div style={{ fontSize: 12, color: '#E2E8F0' }}>
          {sentimentArc.length > 0 ? sentimentArc.join(' -> ') : 'No sentiment history yet'}
        </div>
      </div>

      {hasCustomerSpoken && aiResponse && (
        <div
          style={{
            background: 'rgba(99,102,241,0.1)',
            border: '1px solid rgba(99,102,241,0.3)',
            borderRadius: 8,
            padding: 12,
          }}
        >
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Suggested response
          </div>
          <div style={{ fontSize: 12, color: '#C7D2FE', lineHeight: 1.5 }}>{aiResponse}</div>
        </div>
      )}

      {intent === 'churn_risk' && hasCustomerSpoken && (
        <div
          style={{
            background: 'rgba(239,68,68,0.15)',
            border: '1px solid rgba(239,68,68,0.4)',
            borderRadius: 8,
            padding: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 500, color: '#FCA5A5', marginBottom: 4 }}>
            Churn risk detected
          </div>
          <div style={{ fontSize: 11, color: '#FCA5A5', opacity: 0.8 }}>
            Offer retention discount before the call ends.
          </div>
        </div>
      )}

      {escalationAlert && (
        <div
          style={{
            background: 'rgba(239,68,68,0.2)',
            border: '1px solid rgba(239,68,68,0.45)',
            borderRadius: 8,
            padding: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: '#FCA5A5', marginBottom: 6 }}>
            Escalation Alert
          </div>
          <div style={{ fontSize: 11, color: '#FCA5A5', marginBottom: 10 }}>
            Customer emotion is deteriorating. Offer supervisor handoff or retention intervention now.
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button
              onClick={onEscalate}
              style={{
                padding: '8px 12px',
                background: '#EF4444',
                color: '#fff',
                border: 'none',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                flex: 1,
                minWidth: 140,
              }}
            >
              📞 Escalate to Human
            </button>
            <button
              onClick={onEnableHumanTakeover}
              style={{
                padding: '8px 12px',
                background: 'rgba(99,102,241,0.5)',
                color: '#fff',
                border: '1px solid rgba(99,102,241,0.7)',
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                flex: 1,
                minWidth: 140,
              }}
            >
              👤 Human Takeover
            </button>
          </div>
        </div>
      )}

      {abusiveLanguageDetected && (
        <div
          style={{
            background: 'rgba(239,68,68,0.25)',
            border: '2px solid #EF4444',
            borderRadius: 8,
            padding: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: '#FCA5A5', marginBottom: 6 }}>
            ⚠️ Abusive Language Detected
          </div>
          {abusiveWords && abusiveWords.length > 0 && (
            <div style={{ fontSize: 11, color: '#FCA5A5', marginBottom: 8 }}>
              Flagged: {abusiveWords.join(', ')}
            </div>
          )}
          <div style={{ fontSize: 11, color: '#FCA5A5', marginBottom: 10 }}>
            Immediate escalation required. Transfer to senior agent or supervisor.
          </div>
          <button
            onClick={onEscalate}
            style={{
              width: '100%',
              padding: '10px',
              background: '#EF4444',
              color: '#fff',
              border: 'none',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            🚨 Escalate Immediately
          </button>
        </div>
      )}

      {repeatCallerWarning && (
        <div
          style={{
            background: 'rgba(249,115,22,0.2)',
            border: '1px solid rgba(249,115,22,0.5)',
            borderRadius: 8,
            padding: 12,
          }}
        >
          <div style={{ fontSize: 12, fontWeight: 600, color: '#FED7AA', marginBottom: 4 }}>
            🔄 Repeat Caller Pattern Detected
          </div>
          <div style={{ fontSize: 11, color: '#FDBA74', marginBottom: 8 }}>
            Customer has called {repeatIssueCount || 0}+ times about this issue. Memory:</div>
          <div style={{ fontSize: 11, color: '#FED7AA', backgroundColor: 'rgba(0,0,0,0.2)', padding: 8, borderRadius: 4, marginBottom: 8 }}>
            Previous attempts may not have fully resolved the root cause. Consider root cause analysis or technical review.
          </div>
          <button
            onClick={onEnableHumanTakeover}
            style={{
              width: '100%',
              padding: '8px',
              background: 'rgba(249,115,22,0.6)',
              color: '#fff',
              border: '1px solid rgba(249,115,22,0.8)',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            💡 Take Over (Investigate Root Cause)
          </button>
        </div>
      )}

      {triggerPhrases.length > 0 && (
        <div style={{ background: 'rgba(255,255,255,0.05)', borderRadius: 8, padding: 12 }}>
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Trigger Phrases
          </div>
          <div style={{ fontSize: 12, color: '#E2E8F0' }}>{triggerPhrases.join(', ')}</div>
        </div>
      )}

      {suggestions.length > 0 && (
        <div style={{ background: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.3)', borderRadius: 8, padding: 12 }}>
          <div style={{ fontSize: 10, color: '#94A3B8', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Ranked Agent Assist (2-3 sentence options)
          </div>
          {suggestions.map(s => (
            <div key={s.rank} style={{ marginBottom: 8, paddingBottom: 8, borderBottom: '1px dashed rgba(148,163,184,0.25)' }}>
              <div style={{ fontSize: 11, color: '#86EFAC', marginBottom: 4 }}>
                Option {s.rank} • Likelihood {Math.round((s.resolution_likelihood || 0) * 100)}% • Tone {s.tone_match}
              </div>
              <div style={{ fontSize: 12, color: '#DCFCE7', lineHeight: 1.45 }}>{s.text}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
