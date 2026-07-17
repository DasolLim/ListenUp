"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type WsStatus = "connecting" | "open" | "closed" | "error";

const MAX_BACKOFF_MS = 10_000;

/**
 * Minimal WebSocket client with auto-reconnect (exponential backoff, capped).
 * Reconnects on close/error until unmounted; `send` returns false while offline.
 */
export function useWebSocket(url: string | null) {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [lastMessage, setLastMessage] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const closedRef = useRef(false);

  useEffect(() => {
    if (!url) return;
    closedRef.current = false;

    function connect() {
      if (closedRef.current || !url) return;
      setStatus("connecting");
      let ws: WebSocket;
      try {
        ws = new WebSocket(url);
      } catch {
        setStatus("error");
        scheduleReconnect();
        return;
      }
      wsRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setAttempt(0);
        setStatus("open");
      };
      ws.onmessage = (event) => {
        setLastMessage(typeof event.data === "string" ? event.data : "[binary]");
      };
      ws.onerror = () => {
        setStatus("error");
      };
      ws.onclose = () => {
        wsRef.current = null;
        if (!closedRef.current) {
          setStatus("closed");
          scheduleReconnect();
        }
      };
    }

    function scheduleReconnect() {
      if (closedRef.current) return;
      attemptRef.current += 1;
      setAttempt(attemptRef.current);
      const backoff = Math.min(500 * 2 ** (attemptRef.current - 1), MAX_BACKOFF_MS);
      timerRef.current = setTimeout(connect, backoff);
    }

    connect();

    return () => {
      closedRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [url]);

  const send = useCallback((message: string): boolean => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(message);
      return true;
    }
    return false;
  }, []);

  return { status, lastMessage, send, attempt };
}
