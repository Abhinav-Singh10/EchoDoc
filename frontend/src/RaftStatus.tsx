import { useEffect, useState } from 'react'
import { Code, ConnectError } from '@connectrpc/connect'
import type { ClusterInfo } from './gen/collab/system/v1/system_pb'
import { systemClient } from './rpc'
import { clusterSummary } from './clusterStatus'

export default function RaftStatus() {
  const [cluster, setCluster] = useState<ClusterInfo | null>(null)
  const [failure, setFailure] = useState<{ code: string; message: string } | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined

    async function poll() {
      try {
        const next = await systemClient.getClusterInfo({}, {
          signal: controller.signal, timeoutMs: 2500,
        })
        if (!controller.signal.aborted) {
          for (const node of next.nodes) {
            if (node.result.case === 'error') {
              console.warn('[Raft status] Node check failed', node.nodeId, node.result.value)
            }
          }
          setCluster(next)
          setFailure(null)
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const detail = ConnectError.from(error)
          const diagnostic = { code: Code[detail.code], message: detail.rawMessage }
          console.warn('[Raft status] GetClusterInfo failed', diagnostic, error)
          setFailure(diagnostic)
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

  const nodes = cluster?.nodes ?? []
  const summary = clusterSummary(nodes, failure !== null)

  return (
    <section className="raft-status" aria-label="Cluster status">
      <details className="raft-collapse" open>
        <summary><h2>Cluster status</h2></summary>
        {(failure || !cluster) && <p role="status">{failure ? 'Status check failed — retrying…' : 'Checking cluster…'}</p>}
        <div className="raft-nodes">
          {nodes.map(node => {
            // On a failed aggregate poll, retain only node identities on screen.
            // Previous roles/counters are never presented as fresh observations.
            const info = !failure && node.result.case === 'info' ? node.result.value : null
            const error = failure ?? (node.result.case === 'error' ? node.result.value : null)
            const role = info?.raftRole || 'unknown'
            return (
              <article key={node.nodeId} aria-label={`${node.nodeId} status`}
                className={`raft-node ${!info ? 'raft-node-failed' : role === 'leader' ? 'raft-node-leader' : ''}`}>
                <p className="raft-reachability"><span className="raft-dot" aria-hidden="true" />
                  {info ? 'Reachable' : 'Check failed'}</p>
                <h3>{node.nodeId}</h3>
                <p className="raft-role">{info ? role[0].toUpperCase() + role.slice(1) : 'Status unknown'}</p>
                <p className="raft-term">{info ? `Term ${info.raftTerm}` : 'Retrying…'}</p>
                <dl className="raft-counters">
                  <div><dt>Log</dt><dd>{info?.raftLastLogIndex.toString() ?? '—'}</dd></div>
                  <div><dt>Commit</dt><dd>{info?.raftCommitIndex.toString() ?? '—'}</dd></div>
                  <div><dt>Applied</dt><dd>{info?.raftLastApplied.toString() ?? '—'}</dd></div>
                </dl>
                {error && !failure && <details className="raft-error">
                  <summary>Check error details</summary>
                  <p>{error.code}: {error.message}</p>
                </details>}
              </article>
            )
          })}
        </div>
        <div className="raft-summary">
          <p>Reported leader: <strong>{summary.leader}</strong></p>
          <p>Reachable: <strong>{summary.reachable}/{nodes.length || 'unknown'}</strong>
            {failure && ' (not confirmed this check)'}</p>
        </div>
        {failure && <details className="raft-error">
          <summary>Status check error details</summary>
          <p>{failure.code}: {failure.message}</p>
          <p>This check failed; it does not confirm that every backend is down.</p>
        </details>}
      </details>
    </section>
  )
}
