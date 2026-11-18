import { useEffect, useState } from "react";
import { Code, ConnectError } from "@connectrpc/connect";
import type { LoginResponse } from "./gen/collab/auth/v1/auth_pb";
import { authClient } from "./rpc";
import { backoff, pause, retryable, STREAM_IDLE_TIMEOUT_MS, STREAM_CHECK_INTERVAL_MS } from "./recovery";

export function useSessionMonitor(
  token: string | undefined,
  setSession: (session: LoginResponse | null) => void,
) {
  const [connectionError, setConnectionError] = useState("");
  const [stopped, setStopped] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();

    async function watchSession() {
      let failures = 0;
      while (!controller.signal.aborted) {
        const current = new AbortController();
        const cancel = () => current.abort();
        controller.signal.addEventListener("abort", cancel, { once: true });
        let lastEvent = performance.now();
        const watchdog = setInterval(() => {
          if (performance.now() - lastEvent >= STREAM_IDLE_TIMEOUT_MS) {
            current.abort(new ConnectError("Session stream stopped responding", Code.Unavailable));
          }
        }, STREAM_CHECK_INTERVAL_MS);
        try {
          const stream = authClient.watchSession({}, {
            headers: { authorization: `Bearer ${token}` },
            signal: current.signal,
          });
          for await (const user of stream) {
            if (controller.signal.aborted || !user) return;
            lastEvent = performance.now();
            failures = 0;
            setConnectionError("");
          }
          if (controller.signal.aborted) return;
          throw new ConnectError("Session stream ended", Code.Unavailable);
        } catch (err) {
          if (controller.signal.aborted) return;
          const error = current.signal.aborted ? current.signal.reason : err;
          if (error instanceof ConnectError && error.code === Code.Unauthenticated) {
            setSession(null);
            setConnectionError("Your session expired or is no longer valid. Log in again.");
            return;
          } else if (!retryable(error)) {
            setStopped(true);
            setConnectionError("Session monitoring stopped. Retry the connection.");
            return;
          } else {
            setConnectionError("Session connection lost. Reconnecting automatically…");
          }
        } finally {
          clearInterval(watchdog);
          controller.signal.removeEventListener("abort", cancel);
          current.abort();
        }
        try { await pause(backoff(failures++), controller.signal); }
        catch { return; }
      }
    }

    function leavePage() {
      controller.abort();
      setSession(null);
    }
    void watchSession();
    window.addEventListener("pagehide", leavePage);
    return () => {
      controller.abort();
      window.removeEventListener("pagehide", leavePage);
    };
  }, [token, setSession, attempt]);


  function clearError() {
    setConnectionError("");
    setStopped(false);
  }

  function retryConnection() {
    clearError();
    setAttempt(value => value + 1);
  }

  return { connectionError, stopped, clearError, retryConnection };
}
