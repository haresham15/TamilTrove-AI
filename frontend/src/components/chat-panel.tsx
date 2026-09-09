"use client";

import { useEffect, useRef, useState } from "react";
import { useApp } from "./app-provider";
import { apiClient, ApiClientError, isAbortError } from "../lib/api-client";
import type {
  AgentChatResponse,
  AgentToolCall,
  ClarificationQuestion,
  MovieResult,
} from "../types/api";
import { Icon } from "./icons";
import { MovieCard } from "./movie-card";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  clarification?: ClarificationQuestion | null;
  recommendations?: MovieResult[];
  toolCalls?: AgentToolCall[];
  latencyMs?: number;
}

export function ChatPanel() {
  const { token } = useApp();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string>(() => `session-${Date.now()}`);

  const activeRequest = useRef<AbortController | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (isOpen && !dialog.open) dialog.showModal();
    if (!isOpen && dialog.open) dialog.close();
  }, [isOpen]);

  useEffect(() => () => activeRequest.current?.abort(), []);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  const sendUserMessage = async (text: string) => {
    if (!text.trim() || loading) return;

    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;

    const userMsg: ChatMessage = {
      id: `usr-${Date.now()}`,
      role: "user",
      content: text.trim(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setQuery("");
    setLoading(true);
    setError(null);

    try {
      const res: AgentChatResponse = await apiClient.agentChat(
        text.trim(),
        sessionId,
        controller.signal,
        token,
      );

      const assistantMsg: ChatMessage = {
        id: `asst-${Date.now()}`,
        role: "assistant",
        content: res.message,
        clarification: res.clarification || null,
        recommendations: res.recommendations || [],
        toolCalls: res.tool_calls_executed || res.tool_calls || [],
        latencyMs: res.latency_ms,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      if (isAbortError(err)) return;
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Failed to get a response. Please try again.",
      );
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendUserMessage(query);
  };

  const handleResetSession = () => {
    setMessages([]);
    setSessionId(`session-${Date.now()}`);
    setError(null);
  };

  return (
    <>
      {/* Floating Action Button */}
      <button
        className="button button-primary chat-fab"
        onClick={() => setIsOpen(true)}
        aria-label="Open AI Assistant"
        style={{
          position: "fixed",
          bottom: "24px",
          right: "24px",
          zIndex: 100,
          borderRadius: "50%",
          width: "56px",
          height: "56px",
          padding: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
        }}
      >
        <Icon name="sparkle" width={24} height={24} />
      </button>

      {/* Chat Dialog */}
      <dialog
        ref={dialogRef}
        className="drawer-dialog chat-drawer"
        onClose={() => setIsOpen(false)}
        onCancel={() => setIsOpen(false)}
        onClick={(event) =>
          event.target === event.currentTarget && event.currentTarget.close()
        }
      >
        <section
          className="drawer-panel"
          style={{ width: "450px", maxWidth: "100%", display: "flex", flexDirection: "column", height: "100%" }}
        >
          <header className="dialog-header">
            <div>
              <span className="eyebrow">TamilTrove V4 Agent</span>
              <h2>Conversational Discovery</h2>
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              {messages.length > 0 && (
                <button
                  className="button button-ghost"
                  type="button"
                  onClick={handleResetSession}
                  style={{ fontSize: "0.8rem", padding: "4px 8px" }}
                  title="Start a new conversation"
                >
                  New Chat
                </button>
              )}
              <button
                className="icon-button"
                type="button"
                onClick={() => setIsOpen(false)}
                aria-label="Close chat"
              >
                <Icon name="x" width={21} height={21} />
              </button>
            </div>
          </header>

          <div
            className="chat-content"
            style={{
              flex: 1,
              overflowY: "auto",
              padding: "16px",
              display: "flex",
              flexDirection: "column",
              gap: "16px",
            }}
          >
            {messages.length === 0 && !loading && !error && (
              <div
                className="chat-empty-state"
                style={{ textAlign: "center", color: "var(--text-muted)", marginTop: "40px" }}
              >
                <Icon
                  name="sparkle"
                  width={48}
                  height={48}
                  style={{ opacity: 0.2, marginBottom: "16px" }}
                />
                <p style={{ fontWeight: 500 }}>Autonomous Movie Agent</p>
                <p style={{ fontSize: "0.85rem", maxWidth: "300px", margin: "0 auto 16px auto" }}>
                  Try asking for specific styles, moods, or cinematography:
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxWidth: "320px", margin: "0 auto" }}>
                  <button
                    className="button button-secondary"
                    style={{ fontSize: "0.8rem", textAlign: "left", padding: "8px 12px" }}
                    onClick={() => sendUserMessage("something intense but not action")}
                  >
                    &quot;something intense but not action&quot;
                  </button>
                  <button
                    className="button button-secondary"
                    style={{ fontSize: "0.8rem", textAlign: "left", padding: "8px 12px" }}
                    onClick={() => sendUserMessage("Village drama with warm golden-hour cinematography")}
                  >
                    &quot;Village drama with golden-hour cinematography&quot;
                  </button>
                  <button
                    className="button button-secondary"
                    style={{ fontSize: "0.8rem", textAlign: "left", padding: "8px 12px" }}
                    onClick={() => sendUserMessage("Overlooked 90s investigative thriller")}
                  >
                    &quot;Overlooked 90s investigative thriller&quot;
                  </button>
                </div>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`chat-message ${msg.role === "user" ? "user-message" : "bot-message"}`}
                style={{
                  alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                  background: msg.role === "user" ? "var(--surface-sunken)" : "var(--surface-raised)",
                  padding: "14px",
                  borderRadius: "14px",
                  maxWidth: msg.role === "user" ? "85%" : "100%",
                  width: msg.role === "assistant" ? "100%" : "auto",
                  border: msg.role === "assistant" ? "1px solid var(--border)" : "none",
                }}
              >
                {/* Tool calls execution indicator */}
                {msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "6px",
                      marginBottom: "10px",
                    }}
                  >
                    {msg.toolCalls.map((tc, idx) => (
                      <span
                        key={idx}
                        style={{
                          fontSize: "0.72rem",
                          background: "var(--surface-sunken)",
                          padding: "2px 8px",
                          borderRadius: "12px",
                          color: "var(--text-muted)",
                          border: "1px solid var(--border)",
                        }}
                      >
                        ⚡ {tc.name}
                      </span>
                    ))}
                  </div>
                )}

                <div style={{ lineHeight: "1.5", fontSize: "0.92rem", whiteSpace: "pre-line" }}>
                  {msg.content}
                </div>

                {/* Clarification Choice Chips */}
                {msg.clarification && msg.clarification.options.length > 0 && (
                  <div style={{ marginTop: "12px" }}>
                    <p style={{ fontSize: "0.78rem", textTransform: "uppercase", color: "var(--text-muted)", margin: "0 0 8px 0" }}>
                      Choose a preference:
                    </p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                      {msg.clarification.options.map((opt, oIdx) => (
                        <button
                          key={oIdx}
                          type="button"
                          className="button button-secondary"
                          onClick={() => sendUserMessage(opt)}
                          style={{
                            fontSize: "0.8rem",
                            borderRadius: "16px",
                            padding: "6px 12px",
                          }}
                        >
                          {opt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommended Movie Cards */}
                {msg.recommendations && msg.recommendations.length > 0 && (
                  <div style={{ marginTop: "16px" }}>
                    <h4
                      style={{
                        margin: "0 0 10px 0",
                        fontSize: "0.8rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-muted)",
                      }}
                    >
                      Recommended Titles
                    </h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      {msg.recommendations.slice(0, 3).map((movie, idx) => (
                        <MovieCard key={movie.id} movie={movie} index={idx} />
                      ))}
                    </div>
                  </div>
                )}

                {msg.latencyMs !== undefined && (
                  <div style={{ marginTop: "8px", fontSize: "0.7rem", color: "var(--text-muted)", textAlign: "right" }}>
                    {msg.latencyMs.toFixed(0)} ms • 100% Grounded
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div
                className="chat-message bot-message"
                style={{
                  alignSelf: "flex-start",
                  display: "flex",
                  gap: "8px",
                  alignItems: "center",
                  background: "var(--surface-raised)",
                  padding: "10px 14px",
                  borderRadius: "12px",
                }}
              >
                <span className="spinner" aria-hidden="true" />
                <span style={{ fontSize: "0.88rem", color: "var(--text-muted)" }}>Agent reasoning...</span>
              </div>
            )}

            {error && (
              <div
                className="chat-message error-message"
                style={{
                  color: "var(--text-error)",
                  background: "var(--surface-error)",
                  padding: "12px",
                  borderRadius: "12px",
                }}
              >
                <p style={{ margin: 0 }}>{error}</p>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          <footer
            className="drawer-footer"
            style={{ borderTop: "1px solid var(--border)", padding: "16px" }}
          >
            <form onSubmit={handleSubmit} style={{ display: "flex", gap: "8px", width: "100%" }}>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask or answer clarification..."
                style={{
                  flex: 1,
                  padding: "10px 16px",
                  borderRadius: "24px",
                  border: "1px solid var(--border)",
                  background: "var(--surface)",
                  color: "var(--text)",
                }}
                disabled={loading}
              />
              <button
                type="submit"
                className="button button-primary"
                disabled={loading || !query.trim()}
                style={{ borderRadius: "24px", padding: "0 20px" }}
              >
                Send
              </button>
            </form>
          </footer>
        </section>
      </dialog>
    </>
  );
}
