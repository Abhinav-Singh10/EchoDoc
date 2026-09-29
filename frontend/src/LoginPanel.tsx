import { Code, ConnectError } from '@connectrpc/connect'
import type { LoginResponse } from './gen/collab/auth/v1/auth_pb'
import { authClient } from './rpc'
import { useEffect, useState } from 'react'

type LoginPanelProps = {
  session: LoginResponse | null
  setSession: (session: LoginResponse | null) => void
}

function LoginPanel({ session, setSession }: LoginPanelProps) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const token = session?.sessionToken

useEffect(() => {
  if (!token) return

  const controller = new AbortController()

  async function watchSession() {
    try {
      const stream = authClient.watchSession(
        {},
        {
          headers: {
            authorization: `Bearer ${token}`,
          },
          signal: controller.signal,
        },
      )

      for await (const user of stream) {
        if (controller.signal.aborted) return
        setNotice(`Session active for ${user.username}.`)
      }
      
      if (!controller.signal.aborted) {
        setError('Session stream ended. Restore the connection, then check session.')
      }

    } catch (err) {
      if (controller.signal.aborted) return
    
      if (
        err instanceof ConnectError &&
        err.code === Code.Unauthenticated
      ) {
        setSession(null)
        setError('Your session expired or is no longer valid. Log in again.')
      } else {
        setError('Session connection lost. Restore the connection, then check session.')
      }
    } finally {
      if (!controller.signal.aborted) {
        setNotice('')
      }
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
}, [token, setSession])


async function login() {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const response = await authClient.login(
        { username, password },
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
    if (!session) return

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
  
    try {
      const user = await authClient.getCurrentUser(
        {},
        {
          headers: {
            authorization: `Bearer ${session.sessionToken}`,
          },
          timeoutMs: 5000,
        },
      )
  
      setNotice(`Session accepted by Python for ${user.username}.`)
    } catch (err) {
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
    <section>
      <h2>Account</h2>

      {session ? (
        <div>
        <p>Logged in as {session.user?.username}</p>
      
        <button onClick={checkSession} disabled={busy}>
          Check session
        </button>
      
        <button onClick={logout} disabled={busy}>
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
          <fieldset disabled={busy}>
            <legend>Log in with a demo account</legend>

            <label>
              Username
              <input
                value={username}
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

            <button type="submit">
              {busy ? 'Logging in…' : 'Log in'}
            </button>
          </fieldset>
        </form>
      )}

      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
    </section>
  )
}

export default LoginPanel