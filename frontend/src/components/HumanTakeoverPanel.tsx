import React, { useState } from 'react';
import './HumanTakeoverPanel.css';

interface HumanTakeoverPanelProps {
  sessionId?: string;
  onSendText: (text: string) => void;
  aiSuggestions: Array<{ suggestion: string; tone: string }>;
  isEnabled: boolean;
}

export const HumanTakeoverPanel: React.FC<HumanTakeoverPanelProps> = ({
  onSendText,
  aiSuggestions,
  isEnabled,
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

  if (!isEnabled) {
    return null; // Hidden if not in takeover mode
  }

  return (
    <div className="human-takeover-panel">
      <div className="takeover-header">
        <h3>🤖 → 👤 Human Takeover Mode Active</h3>
        <p className="takeover-notice">
          AI is monitoring. You control the conversation. Type messages to send to customer.
        </p>
      </div>

      <div className="takeover-container">
        {/* Left: Agent Input */}
        <div className="agent-input-section">
          <label>What would you like to say?</label>
          <textarea
            placeholder="Type your response to the customer..."
            value={agentText}
            onChange={(e) => setAgentText(e.target.value)}
            rows={4}
          />
          <button
            onClick={handleSendText}
            disabled={!agentText.trim()}
            className="btn-send-text"
          >
            📢 Send Text (→ TTS)
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
