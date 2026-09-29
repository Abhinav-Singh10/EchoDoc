import { useState } from 'react'
// serverInfo response type for Ts
import type { ServerInfo } from './gen/collab/system/v1/system_pb'
// Stub for calling rpcs
import { systemClient } from './rpc'
import EventStream from './EventStream'
import DocumentList from './DocumentList'
import './App.css'
import LoginPanel from './LoginPanel'
import type { LoginResponse } from './gen/collab/auth/v1/auth_pb'

function App() {
  const [serverInfo, setServerInfo] = useState<ServerInfo | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [session, setSession] = useState<LoginResponse | null>(null)

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
      <h1>System diagnostics</h1>
      <LoginPanel session={session} setSession={setSession} />

      {session && (
        <DocumentList token={session.sessionToken} />
      )}
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
    </main>
  )
}

export default App
