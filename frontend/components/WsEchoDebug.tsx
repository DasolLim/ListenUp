"use client";

import { useState } from "react";
import { useWebSocket } from "@/lib/useWebSocket";

// Temporary Phase 1 debug widget — replaced by the real caption stream in Phase 2.
const statusCopy = {
  connecting: { label: "Connecting…", tone: "text-amber-700 dark:text-amber-400" },
  open: { label: "Connected", tone: "text-green-700 dark:text-green-400" },
  closed: { label: "Disconnected — retrying", tone: "text-red-700 dark:text-red-400" },
  error: { label: "Connection error — retrying", tone: "text-red-700 dark:text-red-400" },
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
      className="mt-8 rounded-lg border border-zinc-300 p-4 dark:border-zinc-700"
    >
      <h2 id="ws-debug-heading" className="font-semibold">
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
          className="flex-1 rounded border border-zinc-300 bg-transparent px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-1 dark:border-zinc-700"
        />
        <button
          type="submit"
          className="rounded bg-zinc-900 px-4 py-2 font-medium text-white hover:bg-zinc-700 focus-visible:outline-2 focus-visible:outline-offset-2 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300"
        >
          Send
        </button>
      </form>
      {sendFailed && (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
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
