import { useCallback, useEffect, useRef, useState } from "react";
import * as SDK from "azure-devops-extension-sdk";

import { ask } from "./api";

interface Message {
  role: "user" | "assistant";
  text: string;
  sources?: string[];
  failed?: boolean;
}

const SUGGESTIONS = [
  "Summarise this work item",
  "What is blocking this?",
  "What do the comments say?",
];

export function App({ workItemId }: { workItemId?: number }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const conversationId = useRef(`wi-${workItemId ?? "new"}-${Date.now()}`);
  const endRef = useRef<HTMLDivElement>(null);

  // The panel is a fixed-height iframe until we tell the host otherwise, so the
  // content is clipped without this.
  useEffect(() => {
    SDK.resize();
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, busy]);

  const send = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || busy) return;

      setInput("");
      setBusy(true);
      setMessages((prev) => [
        ...prev,
        { role: "user", text: trimmed },
        { role: "assistant", text: "" },
      ]);

      const update = (patch: Partial<Message>) =>
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = { ...next[next.length - 1], ...patch };
          return next;
        });

      let answer = "";
      try {
        for await (const event of ask({
          question: trimmed,
          workItemId,
          conversationId: conversationId.current,
        })) {
          if (event.type === "sources") update({ sources: event.sources });
          if (event.type === "token") {
            answer += event.text;
            update({ text: answer });
          }
          if (event.type === "error") update({ text: event.message, failed: true });
        }
      } catch {
        update({ text: "Lost connection to the assistant.", failed: true });
      } finally {
        setBusy(false);
      }
    },
    [busy, workItemId]
  );

  return (
    <div className="panel">
      {messages.length === 0 ? (
        <div className="empty">
          <p className="empty-title">Ask about this work item</p>
          <p className="empty-body">
            Answers are grounded in your project's work items and wiki, with sources.
          </p>
          <div className="suggestions">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="messages">
          {messages.map((message, i) => (
            <div key={i} className={`message ${message.role}`}>
              {message.role === "assistant" && !message.text && busy ? (
                <span className="thinking">
                  <i /> <i /> <i />
                </span>
              ) : (
                <p className={message.failed ? "text failed" : "text"}>{message.text}</p>
              )}
              {message.sources && message.sources.length > 0 && !message.failed && (
                <div className="sources">
                  {dedupe(message.sources).map((source) => (
                    <span key={source} className="source">
                      {source}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div ref={endRef} />
        </div>
      )}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={workItemId ? `Ask about #${workItemId}...` : "Ask a question..."}
          disabled={busy}
          aria-label="Ask a question about this work item"
        />
        <button type="submit" disabled={busy || !input.trim()}>
          {busy ? "..." : "Ask"}
        </button>
      </form>
    </div>
  );
}

function dedupe(values: string[]) {
  return Array.from(new Set(values));
}
