"use client";

import { useEffect, useRef, useState } from "react";
import { useApp } from "./app-provider";
import { apiClient, ApiClientError, isAbortError } from "../lib/api-client";
import type { ChatResponse } from "../types/api";
import { Icon } from "./icons";
import { MovieCard } from "./movie-card";

export function ChatPanel() {
  const { token } = useApp();
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<ChatResponse | null>(null);
  
  const activeRequest = useRef<AbortController | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (isOpen && !dialog.open) dialog.showModal();
    if (!isOpen && dialog.open) dialog.close();
  }, [isOpen]);

  useEffect(() => () => activeRequest.current?.abort(), []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;

    setLoading(true);
    setError(null);
    setResponse(null);

    try {
      const res = await apiClient.chat(query.trim(), controller.signal, token);
      setResponse(res);
    } catch (err) {
      if (isAbortError(err)) return;
      setError(
        err instanceof ApiClientError
          ? err.message
          : "Failed to get a response. Please try again."
      );
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setLoading(false);
      }
    }
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
        <section className="drawer-panel" style={{ width: "400px", maxWidth: "100%" }}>
          <header className="dialog-header">
            <div>
              <span className="eyebrow">Ask AI</span>
              <h2>Conversational Discovery</h2>
            </div>
            <button
              className="icon-button"
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Close chat"
            >
              <Icon name="x" width={21} height={21} />
            </button>
          </header>

          <div className="chat-content" style={{ flex: 1, overflowY: "auto", padding: "16px", display: "flex", flexDirection: "column", gap: "16px" }}>
            {response && (
              <div className="chat-message user-message" style={{ alignSelf: "flex-end", background: "var(--surface-sunken)", padding: "12px", borderRadius: "12px", maxWidth: "90%" }}>
                <p style={{ margin: 0 }}>{response.query}</p>
              </div>
            )}
            
            {loading && (
              <div className="chat-message bot-message" style={{ alignSelf: "flex-start", display: "flex", gap: "8px", alignItems: "center" }}>
                <span className="spinner" aria-hidden="true" />
                <span>Thinking...</span>
              </div>
            )}

            {error && (
              <div className="chat-message error-message" style={{ color: "var(--text-error)", background: "var(--surface-error)", padding: "12px", borderRadius: "12px" }}>
                <p style={{ margin: 0 }}>{error}</p>
              </div>
            )}

            {response && (
              <div className="chat-message bot-message" style={{ alignSelf: "flex-start", background: "var(--surface-raised)", padding: "16px", borderRadius: "12px", width: "100%" }}>
                <div style={{ marginBottom: "16px", lineHeight: "1.5" }}>
                  {response.answer}
                </div>
                
                {response.citations && response.citations.length > 0 && (
                  <div className="chat-citations">
                    <h4 style={{ margin: "0 0 12px 0", fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>
                      Citations
                    </h4>
                    <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                      {response.citations.map((movie, idx) => (
                        <MovieCard key={movie.id} movie={movie} index={idx} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {!response && !loading && !error && (
              <div className="chat-empty-state" style={{ textAlign: "center", color: "var(--text-muted)", marginTop: "40px" }}>
                <Icon name="sparkle" width={48} height={48} style={{ opacity: 0.2, marginBottom: "16px" }} />
                <p>Ask anything about Tamil cinema.</p>
                <p style={{ fontSize: "0.85rem" }}>e.g. &quot;What are some good spy movies starring Kamal Haasan?&quot;</p>
              </div>
            )}
          </div>

          <footer className="drawer-footer" style={{ borderTop: "1px solid var(--border)", padding: "16px" }}>
            <form onSubmit={handleSubmit} style={{ display: "flex", gap: "8px", width: "100%" }}>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask about movies..."
                style={{ flex: 1, padding: "10px 16px", borderRadius: "24px", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)" }}
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
