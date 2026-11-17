import { useEffect, useState } from 'react'
import type { ServerInfo } from './gen/collab/system/v1/system_pb'
import { systemClient } from './rpc'

export default function RaftStatus() {
  const [info, setInfo] = useState<ServerInfo | null>(null)
  const [unavailable, setUnavailable] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined

    async function poll() {
      try {
        const next = await systemClient.getServerInfo({}, {
          signal: controller.signal, timeoutMs: 1000,
        })
        if (!controller.signal.aborted) {
          setInfo(next)
          setUnavailable(false)
        }
      } catch {
        if (!controller.signal.aborted) {
          setInfo(null)
          setUnavailable(true)
        }
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 2000)
      }
    }

    void poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [])

  return (
    <section className="raft-status" aria-label="Connected backend status">
      <p role="status">
        {unavailable ? 'Backend unavailable' : info ? (
          <>Connected backend: <strong>{info.serverId}</strong>
            {' · '}Raft role: <strong>{info.raftRole}</strong>
            {' · '}Term: {info.raftTerm.toString()}
            {' · '}Known leader: {info.raftLeaderId || 'unknown'}
            {' · '}Last log index: {info.raftLastLogIndex.toString()}
            {' · '}Commit index: {info.raftCommitIndex.toString()}</>
        ) : 'Checking backend…'}
      </p>
      <p className="raft-note">This is the connected backend’s view. The gateway stays on app-1;
        documents are not replicated yet. Committed log entries are not applied to documents yet.</p>
    </section>
  )
}
