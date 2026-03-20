import React, { useState } from 'react';
import './HumanTakeoverPanel.css';

interface HumanTakeoverPanelProps {
  sessionId?: string;
  onSendText: (text: string) => void;
  aiSuggestions: Array<{ suggestion: string; tone: string }>;
  isEnabled: boolean;
  onToggleTakeover: () => void;
}

export const HumanTakeoverPanel: React.FC<HumanTakeoverPanelProps> = ({
  onSendText,
  aiSuggestions,
  isEnabled,
  onToggleTakeover,
}: HumanTakeoverPanelProps) => {
  const [agentText, setAgentText] = useState('');
  const [sentMessages, setSentMessages] = useState<string[]>([]);

  const handleSendText = () => {
    if (agentText.trim()) {
      onSendText(agentText);
      setSentMessages([...sentMessages, agentText]);
      setAgentText('');
    }
  };

  const handleUseSuggestion = (suggestion: string) => {
    setAgentText(suggestion);
  };

  return (
    <div className={`human-takeover-panel ${isEnabled ? 'enabled' : 'disabled'}`}>
      <div className="takeover-header">
        <h3>{isEnabled ? '🤖 -> 👤 Human Takeover Active' : 'Manual Agent Console'}</h3>
        <button className="takeover-toggle-btn" onClick={onToggleTakeover}>
          {isEnabled ? 'Return AI Control' : 'Take Control'}
        </button>
        <p className="takeover-notice">
          {isEnabled
            ? 'AI is assisting in background. Type and send responses directly to customer.'
            : 'Enable takeover to type manual responses, or wait for escalation trigger.'}
        </p>
      </div>

      <div className="takeover-container">
        {/* Left: Agent Input */}
        <div className="agent-input-section">
          <label>What would you like to say?</label>
          <textarea
            placeholder={
              isEnabled
                ? 'Type your response to the customer...'
                : 'Click "Take Control" to start manual typing...'
            }
            value={agentText}
            onChange={(e) => setAgentText(e.target.value)}
            rows={4}
            disabled={!isEnabled}
          />
          <button
            onClick={handleSendText}
            disabled={!isEnabled || !agentText.trim()}
            className="btn-send-text"
          >
            Send Text (TTS)
          </button>
        </div>

        {/* Right: AI Suggestions */}
        <div className="ai-suggestions-section">
          <h4>💡 AI Suggestions (Optional)</h4>
          <div className="suggestions-list">
            {aiSuggestions && aiSuggestions.length > 0 ? (
              aiSuggestions.map((sugg, idx) => (
                <div
                  key={idx}
                  className="suggestion-item"
                  onClick={() => handleUseSuggestion(sugg.suggestion)}
                >
                  <div className="sugg-tone">{sugg.tone}</div>
                  <div className="sugg-text">{sugg.suggestion}</div>
                  <div className="sugg-action">Click to use →</div>
                </div>
              ))
            ) : (
              <p className="no-suggestions">No suggestions available</p>
            )}
          </div>
        </div>
      </div>

      {/* Message History */}
      {sentMessages.length > 0 && (
        <div className="sent-messages">
          <h5>Messages Sent:</h5>
          <div className="messages-log">
            {sentMessages.map((msg, idx) => (
              <div key={idx} className="sent-msg">
                ✓ {msg}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
