"use client";

import { useState } from "react";
import { useWebSocket } from "@/lib/useWebSocket";

// Temporary Phase 1 debug widget — replaced by the real caption stream in Phase 2.
const statusCopy = {
  connecting: { label: "Connecting…", tone: "text-warning-strong" },
  open: { label: "Connected", tone: "text-success-strong" },
  closed: { label: "Disconnected — retrying", tone: "text-error-strong" },
  error: { label: "Connection error — retrying", tone: "text-error-strong" },
} as const;

export default function WsEchoDebug() {
  const backend = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";
  const wsUrl = backend.replace(/^http/, "ws") + "/ws/echo";
  const { status, lastMessage, send, attempt } = useWebSocket(wsUrl);
  const [input, setInput] = useState("hello from ListenUp");
  const [sendFailed, setSendFailed] = useState(false);

  return (
    <section
      aria-labelledby="ws-debug-heading"
      className="glass-card mt-6 max-w-2xl p-6"
    >
      <h2 id="ws-debug-heading" className="font-display text-[18px] font-semibold">
        WebSocket debug (temporary)
      </h2>
      <p role="status" className={`mt-1 text-sm ${statusCopy[status].tone}`}>
        {statusCopy[status].label}
        {attempt > 0 && status !== "open" ? ` (attempt ${attempt})` : ""}
      </p>
      <form
        className="mt-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setSendFailed(!send(input));
        }}
      >
        <label htmlFor="ws-message" className="sr-only">
          Message to echo
        </label>
        <input
          id="ws-message"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="glass-strong min-w-0 flex-1 rounded-xl border border-white/60 px-3.5 py-2.5 text-ink shadow-glass outline-none placeholder:text-ink-faint"
        />
        <button
          type="submit"
          className="btn-primary rounded-full px-5 py-2.5 text-sm font-semibold text-on-accent"
        >
          Send
        </button>
      </form>
      {sendFailed && (
        <p role="alert" className="mt-2 text-sm text-error-strong">
          Not connected — message not sent. It will work again once reconnected.
        </p>
      )}
      {lastMessage !== null && (
        <p className="mt-3 text-sm">
          Echo: <span className="font-mono">{lastMessage}</span>
        </p>
      )}
    </section>
  );
}
