import { Code, ConnectError } from "@connectrpc/connect";
import type { LoginResponse } from "./gen/collab/auth/v1/auth_pb";
import { authClient } from "./rpc";
import { useState } from "react";
import type { ReactNode } from "react";
import { useSessionMonitor } from "./useSessionMonitor";

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
  const {
    connectionError, stopped: monitorStopped, clearError: clearMonitorError, retryConnection,
  } = useSessionMonitor(session?.sessionToken, setSession);

  async function login() {
    clearMonitorError();
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
      clearMonitorError();
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
        {(error || connectionError) && <p role="alert">{error || connectionError}</p>}
      </section>}

      {session && (error || connectionError) && <div className="session-alert" role="alert">
        <p>{error || connectionError}</p>
        {monitorStopped && <button type="button" onClick={retryConnection}>Retry connection</button>}
      </div>}
    </>
  );
}

export default LoginPanel;
