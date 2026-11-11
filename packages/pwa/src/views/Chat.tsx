import { useState, useRef, useEffect, useCallback } from "react";
import { connectChat, getHistory, loadCheckpoint, saveCheckpoint, type WSMessage } from "../api";
import { CHECKPOINT_SAVE_DEBOUNCE_MS } from "../config";
import { useSpeechRecognition } from "../useSpeechRecognition";
import "./Chat.css";

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  timestamp: Date;
  pending?: boolean;
}

export function ChatView() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [sending, setSending] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [checkpointAvailable, setCheckpointAvailable] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<ReturnType<typeof connectChat> | null>(null);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const {
    supported: voiceSupported,
    listening,
    toggle: toggleVoice,
  } = useSpeechRecognition((text) =>
    setInput((prev) => (prev ? `${prev} ${text}` : text)),
  );

  const handleIncoming = useCallback((msg: WSMessage) => {
    setSending(false);
    setMessages((prev) => {
      // Skip messages we already have (e.g. from loaded history).
      if (prev.some((m) => m.id === msg.id)) return prev;
      // Clear pending flags on all user messages (they've been flushed)
      const cleared = prev.map((m) =>
        m.pending ? { ...m, pending: false } : m,
      );
      return [
        ...cleared,
        {
          id: msg.id,
          role: "assistant" as const,
          text: msg.text,
          timestamp: new Date(msg.timestamp),
        },
      ];
    });
    setPendingCount(0);
  }, []);

  // Load persisted history once on mount.
  useEffect(() => {
    let cancelled = false;
    getHistory()
      .then((history) => {
        if (cancelled) return;
        setMessages((prev) => {
          const seen = new Set(prev.map((m) => m.id));
          const loaded = history
            .filter((h) => !seen.has(h.id))
            .map((h) => ({
              id: h.id,
              role: h.role === "assistant" ? ("assistant" as const) : ("user" as const),
              text: h.text,
              timestamp: new Date(h.timestamp),
            }));
          return [...loaded, ...prev];
        });
      })
      .catch(() => {
        // No history / unauthorized — start with an empty conversation.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Load checkpoint from kernel session store for cross-device continuity.
  useEffect(() => {
    let cancelled = false;
    loadCheckpoint()
      .then((cp) => {
        if (cancelled) return;
        if (cp === null || cp.available === false) {
          setCheckpointAvailable(false);
          return;
        }
        setCheckpointAvailable(true);
        if (cp.messages.length === 0) return;
        setMessages((prev) => {
          if (prev.length > 0) return prev; // history already loaded
          return cp.messages.map((m, idx) => ({
            id: `ckpt-${idx}`,
            role: m.role === "assistant" ? ("assistant" as const) : ("user" as const),
            text: m.content,
            timestamp: new Date(),
          }));
        });
      })
      .catch(() => {
        // checkpoint unavailable — continue with empty chat
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-save checkpoint debounced whenever messages change.
  useEffect(() => {
    if (!checkpointAvailable || messages.length === 0) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      const payload = {
        session_id: "pwa-session",
        messages: messages.map((m) => ({
          role: m.role,
          content: m.text,
        })),
        summary: messages.length > 0
          ? `Last ${messages.length} messages from PWA session`
          : "",
        turns: messages.filter((m) => m.role === "user").length,
      };
      saveCheckpoint(payload).catch(() => {
        // silently fail — checkpoint is best-effort
      });
    }, CHECKPOINT_SAVE_DEBOUNCE_MS);
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, [checkpointAvailable, messages]);

  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      const ws = connectChat(handleIncoming);
      wsRef.current = ws;

      // Poll connection state briefly to detect open/close
      const check = setInterval(() => {
        const state = ws.getState();
        if (state === WebSocket.OPEN) {
          setConnected(true);
          setPendingCount(ws.getPendingCount());
          clearInterval(check);
        } else if (state === WebSocket.CLOSED) {
          setConnected(false);
          clearInterval(check);
          reconnectTimer = setTimeout(connect, 3000);
        }
      }, 200);
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [handleIncoming]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    const text = input.trim();
    if (!text || sending || !wsRef.current) return;

    const isOffline = !connected;
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text,
      timestamp: new Date(),
      pending: isOffline,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    if (!isOffline) setSending(true);

    wsRef.current.send(text);
    if (isOffline) setPendingCount(wsRef.current.getPendingCount());
  }

  return (
    <div className="chat">
      <h1 className="chat-title">
        Animus
        <span className={`chat-status ${connected ? "chat-status--ok" : "chat-status--off"}`}>
          {connected ? "connected" : "offline"}
        </span>
        {pendingCount > 0 && (
          <span className="chat-status chat-status--off">
            {pendingCount} pending
          </span>
        )}
      </h1>
      <div className="chat-messages">
        {messages.length === 0 && (
          <p className="chat-empty">Start a conversation.</p>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-bubble chat-bubble--${msg.role}${msg.pending ? " chat-msg--pending" : ""}`}>
            {msg.text}
          </div>
        ))}
        {sending && (
          <div className="chat-bubble chat-bubble--assistant chat-bubble--thinking">
            Thinking...
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input-row">
        <input
          className="chat-input"
          type="text"
          placeholder="Message Animus..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          disabled={sending}
        />
        {voiceSupported && (
          <button
            className={`chat-mic ${listening ? "chat-mic--active" : ""}`}
            onClick={toggleVoice}
            aria-label={listening ? "Stop voice input" : "Start voice input"}
            title="Voice input"
          >
            🎤
          </button>
        )}
        <button
          className="chat-send"
          onClick={handleSend}
          disabled={sending || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
