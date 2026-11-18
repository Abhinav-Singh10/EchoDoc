import { useCallback, useState } from 'react'
import DocumentList from './DocumentList'
import LoginPanel from './LoginPanel'
import RaftStatus from './RaftStatus'
import type { LoginResponse } from './gen/collab/auth/v1/auth_pb'
import './App.css'
import './demo.css'

function App() {
  const [pendingCount, setPendingCount] = useState(0)
  const [session, setSession] = useState<LoginResponse | null>(null)

  const [lastSession, setLastSession] = useState<LoginResponse | null>(null)
  const changeSession = useCallback((next: LoginResponse | null) => {
    setSession(next)
    if (next) setLastSession(next)
  }, [])

  const canLogout = pendingCount === 0
  const lockedUsername = pendingCount ? lastSession?.user?.username : undefined
  const documentToken = session?.sessionToken ?? ''

  return (
    <main>
      <LoginPanel
        session={session}
        setSession={changeSession}
        canLogout={canLogout}
        lockedUsername={lockedUsername}
      >
        <RaftStatus />
      </LoginPanel>

      {lastSession && (
        <DocumentList
          key={lastSession.user?.userId}
          token={documentToken}
          pendingCount={pendingCount}
          onPendingChange={setPendingCount}
        />
      )}
    </main>
  )
}

export default App
