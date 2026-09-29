import { useCallback, useState } from 'react'
import DocumentList from './DocumentList'
import './App.css'
import './demo.css'
import LoginPanel from './LoginPanel'
import type { LoginResponse } from './gen/collab/auth/v1/auth_pb'

function App() {
  const [pendingCount, setPendingCount] = useState(0)
  const [session, setSession] = useState<LoginResponse | null>(null)

  const [lastSession, setLastSession] = useState<LoginResponse | null>(null)
  const changeSession = useCallback((next: LoginResponse | null) => {
    setSession(next)
    if (next) setLastSession(next)
  }, [])

  return (
    <main>
      <header>
        <h1>EchoDoc</h1>
        <p className="eyebrow">ADVANCED OPERATING SYSTEMS · MILESTONE 1</p>
        <p>Collaborative notes with real-time editing and local AI assistance.</p>
      </header>
      <LoginPanel session={session} setSession={changeSession} canLogout={pendingCount === 0}
        lockedUsername={pendingCount ? lastSession?.user?.username : undefined} />

      {lastSession && (
        <DocumentList key={lastSession.user?.userId} token={session?.sessionToken ?? ""} pendingCount={pendingCount} onPendingChange={setPendingCount} />
      )}
    </main>
  )
}

export default App
