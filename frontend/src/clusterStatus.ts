import type { ClusterNodeStatus } from './gen/collab/system/v1/system_pb'

export function clusterSummary(nodes: ClusterNodeStatus[], checkFailed = false) {
  if (checkFailed) return { reachable: 0, leader: 'Unknown — status check failed' }
  const infos = nodes.flatMap(node => node.result.case === 'info' ? [node.result.value] : [])
  const reported = new Set(infos.flatMap(info => [
    ...(info.raftLeaderId ? [info.raftLeaderId] : []),
    ...(info.raftRole === 'leader' ? [info.serverId] : []),
  ]))
  let leader = 'Not yet confirmed'
  if (reported.size > 1) leader = 'Views differ — election may be settling'
  else if (infos.some(info => info.raftRole === 'candidate')) leader = 'Election in progress'
  else if (reported.size === 1) leader = [...reported][0]
  else if (infos.length > 0 && infos.every(info => info.raftRole === 'disabled')) leader = 'Raft disabled'
  return { reachable: infos.length, leader }
}
