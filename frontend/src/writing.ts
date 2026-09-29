import type { Action } from './gen/collab/ai/v1/ai_pb'

// A preview belongs to one exact document/selection/session state.
export type WritingTarget = {
  action: Action
  text: string
  context: string
  from: number
  to: number
  revision: bigint
  version: number
  token: string
}
export type WritingEditor = {
  capture: (action: Action) => WritingTarget
}
