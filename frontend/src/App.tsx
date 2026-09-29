import { useCallback, useState } from 'react'
// serverInfo response type for Ts
import type { ServerInfo } from './gen/collab/system/v1/system_pb'
// Stub for calling rpcs
import { systemClient } from './rpc'
import EventStream from './EventStream'
import DocumentList from './DocumentList'
import './App.css'
import './demo.css'
import LoginPanel from './LoginPanel'
import type { LoginResponse } from './gen/collab/auth/v1/auth_pb'

function App() {
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [pendingCount, setPendingCount] = useState(0)
  const [session, setSession] = useState<LoginResponse | null>(null)

  const [lastSession, setLastSession] = useState<LoginResponse | null>(null)
  const changeSession = useCallback((next: LoginResponse | null) => {
    setSession(next)
    if (next) setLastSession(next)
  }, [])

  async function loadServerInfo() {
    setLoading(true)
    setError('')
    setServerInfo(null)

    try {
      const response = await systemClient.getServerInfo({}, { timeoutMs: 5000 })
      setServerInfo(response)
    } catch {
      setError('Could not get server info. Check Python and Envoy, then retry.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main>
      <header><p className="eyebrow">ADVANCED OPERATING SYSTEMS · MILESTONE 1</p>
        <h1>Shared Notes</h1><p>Write together. Keep your ideas in sync.</p></header>
      <LoginPanel session={session} setSession={changeSession} canLogout={pendingCount === 0}
        lockedUsername={pendingCount ? lastSession?.user?.username : undefined} />

      {lastSession && (
        <DocumentList key={lastSession.user?.userId} token={session?.sessionToken ?? ""} pendingCount={pendingCount} onPendingChange={setPendingCount} />
      )}
      <details className="diagnostics"><summary>System diagnostics</summary>
      <button onClick={loadServerInfo} disabled={loading}>
        {loading ? 'Connecting…' : 'Get server info'}
      </button>

      {error && <p role="alert">{error}</p>}

      {serverInfo && (
        <section aria-label="Server information">
          <h2>Server response</h2>

          <dl>
            <dt>Server ID</dt>
            <dd>{serverInfo.serverId}</dd>

            <dt>Process instance ID</dt>
            <dd>{serverInfo.processInstanceId}</dd>

            <dt>Application version</dt>
            <dd>{serverInfo.applicationVersion}</dd>

            <dt>Uptime at request</dt>
            <dd>{serverInfo.uptimeSeconds.toFixed(2)} seconds</dd>
          </dl>
        </section>
      )}
      <EventStream/>
      </details>
      <footer>React + Yjs → gRPC-Web / Envoy → Python + SQLite · Local Qwen assistance</footer>
    </main>
  )
}

export default App
