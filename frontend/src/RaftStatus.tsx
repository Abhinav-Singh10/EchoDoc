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
    <section className="raft-status" aria-label="Responding backend status">
      <p role="status">
        {unavailable ? 'Backend unavailable' : info ? (
          <>Responding backend: <strong>{info.serverId}</strong>
            {' · '}Raft role: <strong>{info.raftRole}</strong>
            {' · '}Term: {info.raftTerm.toString()}
            {' · '}Known leader: {info.raftLeaderId || 'unknown'}
            {' · '}Last log index: {info.raftLastLogIndex.toString()}
            {' · '}Commit index: {info.raftCommitIndex.toString()}
            {' · '}Applied index: {info.raftLastApplied.toString()}</>
        ) : 'Checking backend…'}
      </p>
      <p className="raft-note">This is the responding backend’s view. The gateway uses available backends;
        writes forward to the leader and reads confirm Raft progress. Streams reconnect automatically.</p>
    </section>
  )
}
