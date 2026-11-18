import { Code, ConnectError } from "@connectrpc/connect";
import type { LoginResponse } from "./gen/collab/auth/v1/auth_pb";
import { authClient } from "./rpc";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { backoff, pause, retryable } from "./recovery";

type LoginPanelProps = {
  children: ReactNode;
  canLogout: boolean;
  lockedUsername?: string;
  session: LoginResponse | null;
  setSession: (session: LoginResponse | null) => void;
};

function LoginPanel({ session, setSession, canLogout, lockedUsername, children }: LoginPanelProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [monitorError, setMonitorError] = useState("");
  const [monitorStopped, setMonitorStopped] = useState(false);
  const token = session?.sessionToken;
  const [watchAttempt, setWatchAttempt] = useState(0);

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
          if (performance.now() - lastEvent >= 6000) {
            current.abort(new ConnectError("Session stream stopped responding", Code.Unavailable));
          }
        }, 250);
        try {
          const stream = authClient.watchSession({}, {
            headers: { authorization: `Bearer ${token}` },
            signal: current.signal,
          });
          for await (const user of stream) {
            if (controller.signal.aborted || !user) return;
            lastEvent = performance.now();
            failures = 0;
            setMonitorError("");
          }
          if (controller.signal.aborted) return;
          throw new ConnectError("Session stream ended", Code.Unavailable);
        } catch (err) {
          if (controller.signal.aborted) return;
          const error = current.signal.aborted ? current.signal.reason : err;
          if (error instanceof ConnectError && error.code === Code.Unauthenticated) {
            setSession(null);
            setMonitorError("Your session expired or is no longer valid. Log in again.");
            return;
          } else if (!retryable(error)) {
            setMonitorStopped(true);
            setMonitorError("Session monitoring stopped. Retry the connection.");
            return;
          } else {
            setMonitorError("Session connection lost. Reconnecting automatically…");
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
  }, [token, setSession, watchAttempt]);

  async function login() {
    setMonitorError("");
    setMonitorStopped(false);
    setBusy(true);
    setError("");
    try {
      const response = await authClient.login(
        { username: lockedUsername || username, password }, { timeoutMs: 5000 },
      );
      setSession(response);
      setPassword("");
    } catch (err) {
      setError(err instanceof ConnectError && err.code === Code.Unauthenticated
        ? "Incorrect username or password."
        : "Login failed. Check Python and Envoy.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    if (!session || !canLogout || busy) return;
    setBusy(true);
    setError("");
    try {
      await authClient.logout({}, {
        headers: { authorization: `Bearer ${session.sessionToken}` }, timeoutMs: 5000,
      });
      setMonitorError("");
      setMonitorStopped(false);
      setSession(null);
    } catch (err) {
      if (err instanceof ConnectError && err.code === Code.Unauthenticated) {
        setSession(null);
        setError("Your session is no longer valid. Log in again.");
      } else {
        setError("Logout failed. Check Python and Envoy, then retry.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header>
        <div className="app-title-row">
          <h1>EchoDoc</h1>
          {session && <button type="button" onClick={logout} disabled={busy || !canLogout}>
            {busy ? "Logging out…" : "Log out"}
          </button>}
        </div>
        <p>Collaborative notes with real-time editing and local AI assistance.</p>
      </header>

      {children}

      {!session && <section className="login-card">
        <h2>Log in</h2>
        <form onSubmit={event => { event.preventDefault(); void login(); }}>
          <fieldset disabled={busy} aria-label="Log in">
            <label>
              Username
              <input
                value={lockedUsername || username}
                readOnly={!!lockedUsername}
                onChange={event => setUsername(event.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={event => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <button type="submit">{busy ? "Logging in…" : "Log in"}</button>
          </fieldset>
        </form>
        {(error || monitorError) && <p role="alert">{error || monitorError}</p>}
      </section>}

      {session && (error || monitorError) && <div className="session-alert" role="alert">
        <p>{error || monitorError}</p>
        {monitorStopped && <button type="button" onClick={() => {
          setMonitorStopped(false);
          setMonitorError("");
          setWatchAttempt(attempt => attempt + 1);
        }}>Retry connection</button>}
      </div>}
    </>
  );
}

export default LoginPanel;
