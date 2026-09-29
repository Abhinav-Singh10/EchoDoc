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
      <header><p className="eyebrow">ADVANCED OPERATING SYSTEMS · MILESTONE 1</p>
        <h1>Shared Notes</h1><p>Write together. Keep your ideas in sync.</p></header>
      <LoginPanel session={session} setSession={changeSession} canLogout={pendingCount === 0}
        lockedUsername={pendingCount ? lastSession?.user?.username : undefined} />

      {lastSession && (
        <DocumentList key={lastSession.user?.userId} token={session?.sessionToken ?? ""} pendingCount={pendingCount} onPendingChange={setPendingCount} />
      )}
    </main>
  )
}

export default App
