/**
 * Hook for managing WebSocket connections to backend.
 * Handles real-time chat streaming and live updates.
 */

import { useEffect, useRef, useCallback, useState } from "react";
import * as Types from "../types";
import * as api from "../services/api";

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [liveMessage, setLiveMessage] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const reconnectAttemptsRef = useRef(0);
  const MAX_RECONNECT_ATTEMPTS = 5;
  const BASE_RECONNECT_DELAY = 1000; // ms

  /**
   * Connect to WebSocket.
   */
  const connect = useCallback(() => {
    if (!sessionId) return;

    try {
      const ws = api.openWebSocket(sessionId);

      ws.onopen = () => {
        console.log("WebSocket connected");
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const message = JSON.parse(event.data) as Types.WSMessageUpdate;
          setLiveMessage(message);
        } catch (err) {
          console.error("Failed to parse WebSocket message:", err);
        }
      };

      ws.onerror = () => {
        setError("WebSocket error occurred");
      };

      ws.onclose = () => {
        console.log("WebSocket closed");
        setIsConnected(false);

        // Attempt reconnection with exponential backoff
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delay = BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttemptsRef.current);
          setTimeout(() => {
            reconnectAttemptsRef.current++;
            connect();
          }, delay);
        } else {
          setError("Failed to maintain WebSocket connection");
        }
      };

      wsRef.current = ws;
    } catch (err) {
      console.error("WebSocket connection error:", err);
      setError("Failed to connect to server");
    }
  }, [sessionId]);

  /**
   * Send message over WebSocket.
   */
  const send = useCallback((message: Types.WSMessage) => {
    if (wsRef.current && isConnected) {
      api.sendWSMessage(wsRef.current, message);
    } else {
      console.warn("WebSocket not connected");
    }
  }, [isConnected]);

  /**
   * Send audio chunk (streaming transcript).
   */
  const sendAudioChunk = useCallback(
    (transcript: string) => {
      send({
        type: "audio_chunk",
        data: { transcript },
      });
    },
    [send]
  );

  /**
   * Send user message.
   */
  const sendUserMessage = useCallback(
    (text: string) => {
      send({
        type: "user_message",
        data: { message: text },
      });
    },
    [send]
  );

  /**
   * End call over WebSocket.
   */
  const endCall = useCallback(() => {
    send({
      type: "end_call",
      data: {},
    });
  }, [send]);

  /**
   * Trigger escalation over WebSocket.
   */
  const triggerEscalation = useCallback(() => {
    send({
      type: "escalate",
      data: {},
    });
  }, [send]);

  /**
   * Restore AI control over WebSocket.
   */
  const restoreAI = useCallback(() => {
    send({
      type: "restore_ai",
      data: {},
    });
  }, [send]);

  /**
   * Auto-connect when sessionId changes.
   */
  useEffect(() => {
    if (sessionId) {
      connect();
    }

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [sessionId, connect]);

  return {
    isConnected,
    error,
    liveMessage,
    send,
    sendAudioChunk,
    sendUserMessage,
    endCall,
    triggerEscalation,
    restoreAI,
  };
}

/**
 * Hook for listening to WebSocket updates and processing them.
 */
export function useWebSocketListener(
  onTranscriptUpdate?: (transcript: Types.Message) => void,
  onAIUpdate?: (update: Types.AIUpdate) => void,
  onSummary?: (summary: Types.CallSummary) => void,
  onEscalation?: (alert: Types.EscalationAlert) => void
) {
  return (message: Types.WSMessageUpdate | null) => {
    if (!message) return;

    switch (message.type) {
      case "transcript_update":
        onTranscriptUpdate?.(message.data as Types.Message);
        break;

      case "ai_update":
        onAIUpdate?.(message.data as Types.AIUpdate);
        break;

      case "call_summary":
        onSummary?.(message.data as Types.CallSummary);
        break;

      case "escalation":
        onEscalation?.(message.data as Types.EscalationAlert);
        break;

      case "sentiment_change":
        // Handle sentiment changes if needed
        console.log("Sentiment change:", message.data);
        break;

      default:
        console.warn("Unknown WebSocket message type:", message.type);
    }
  };
}
