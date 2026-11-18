import { Code, ConnectError } from "@connectrpc/connect";
import type { LoginResponse } from "./gen/collab/auth/v1/auth_pb";
import { authClient } from "./rpc";
import { useEffect, useRef, useState } from "react";
import { backoff, pause, retryable, retryRead } from "./recovery";

type LoginPanelProps = {
  canLogout: boolean;
  lockedUsername?: string;
  session: LoginResponse | null;
  setSession: (session: LoginResponse | null) => void;
};

function LoginPanel({ session, setSession, canLogout, lockedUsername }: LoginPanelProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [monitorError, setMonitorError] = useState("");
  const [notice, setNotice] = useState("");
  const token = session?.sessionToken;
  const [watchAttempt, setWatchAttempt] = useState(0);
  const monitor = useRef<AbortController | null>(null);

  useEffect(() => {
    if (!token) return;

    const controller = new AbortController();
    monitor.current = controller;

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
          const stream = authClient.watchSession(
            {},
            {
              headers: { authorization: `Bearer ${token}` },
              signal: current.signal,
            },
          );
          for await (const user of stream) {
            if (controller.signal.aborted) return;
            lastEvent = performance.now();
            failures = 0;
            setMonitorError("");
            setNotice(`Session active for ${user.username}.`);
          }

          if (controller.signal.aborted) return;
          throw new ConnectError("Session stream ended", Code.Unavailable);
        } catch (err) {
          if (controller.signal.aborted) return;
          const error = current.signal.aborted ? current.signal.reason : err;

          if (error instanceof ConnectError && error.code === Code.Unauthenticated) {
            setNotice("");
            setSession(null);
            setMonitorError("Your session expired or is no longer valid. Log in again.");
            return;
          } else if (!retryable(error)) {
            setNotice("");
            setMonitorError("Session monitoring stopped. Check session to try again.");
            return;
          } else {
            setNotice("");
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
      controller.abort()
      setSession(null)
      setNotice('')
    }
  
    watchSession()
    window.addEventListener('pagehide', leavePage)
  
    return () => {
      controller.abort()
      window.removeEventListener('pagehide', leavePage)
    }
  }, [token, setSession, watchAttempt])
  
  async function login() {
    setMonitorError('')
  
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const response = await authClient.login(
        { username: lockedUsername || username, password },
        { timeoutMs: 5000 },
      )
      setSession(response)
      setPassword('')
    } catch (err) {
      if (err instanceof ConnectError && err.code === Code.Unauthenticated) {
        setError('Incorrect username or password.')
      } else {
        setError('Login failed. Check Python and Envoy.')
      }
    } finally {
      setBusy(false)
    }
  }

  async function logout() {
    if (!session || !canLogout) return

    setBusy(true)
    setError('')
    setNotice('')
    try {
      await authClient.logout(
        {},
        {
          headers: {
            authorization: `Bearer ${session.sessionToken}`,
          },
          timeoutMs: 5000,
        },
      )
      setNotice('')
      setMonitorError('')
      setSession(null)
    } catch (err) {
      if (err instanceof ConnectError && err.code === Code.Unauthenticated) {
        setSession(null)
        setError('Your session is no longer valid. Log in again.')
      } else {
        setError('Logout failed. Check Python and Envoy, then retry.')
      }
    } finally {
      setBusy(false)
    }
  }

  async function checkSession() {
    if (!session) return
  
    setBusy(true)
    setError('')
    setNotice('')
  
    const signal = monitor.current?.signal;
    try {
      const user = await retryRead(timeoutMs => authClient.getCurrentUser(
        {},
        {
          headers: {
            authorization: `Bearer ${session.sessionToken}`,
          },
          timeoutMs, signal,
        },
      ), signal)
      if (signal?.aborted) return
  
      setNotice(`Session accepted for ${user.username}.Restarting monitor...`)
      setWatchAttempt(attempt => attempt+1)
    } catch (err) {
      if (signal?.aborted) return
      if (err instanceof ConnectError && err.code === Code.Unauthenticated) {
        setSession(null)
        setError('Your session expired or is no longer valid. Log in again.')
      } else {
        setError('Could not check the session. Check Python and Envoy.')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className={`account-panel ${session? "": "login-card"}`}>
      <h2>{session? "Account":"Log in"}</h2>

      {session ? (
        <div>
        <p>Logged in as {session.user?.username}</p>
      
        <button onClick={checkSession} disabled={busy}>
          Check session
        </button>
      
        <button onClick={logout} disabled={busy || !canLogout}>
          Log out
        </button>
      
        {busy && <p role="status">Working…</p>}
      </div>
      ) : (
        <form
          onSubmit={event => {
            event.preventDefault()
            login()
          }}
        >
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
                onChange={(event) => setPassword(event.target.value)}                
                autoComplete="current-password"
                required
              />
            </label>

            <button type="submit">
              {busy ? 'Logging in…' : 'Log in'}
            </button>
          </fieldset>
        </form>
      )}

      {(error || monitorError) && <p role="alert">{error || monitorError}</p>}
      {notice && <p role="status">{notice}</p>}
    </section>
  )
}

export default LoginPanel
