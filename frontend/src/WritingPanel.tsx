import { useEffect, useEffectEvent, useRef, useState } from 'react'
import type { RefObject } from 'react'
import { Action } from './gen/collab/ai/v1/ai_pb'
import { writingClient } from './rpc'
import type { WritingEditor, WritingTarget } from './writing'

type Props = { editorRef: RefObject<WritingEditor | null>; documentId: string; token: string; ready: boolean; version: number; revision: bigint | null; lastTyped: number }
export default function WritingPanel({ editorRef, documentId, token, ready, version, revision, lastTyped }: Props) {
  const [auto, setAuto] = useState(false)
  const lastSuggested = useRef(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<{ target: WritingTarget; answer: string } | null>(null)
  const active = useRef<AbortController | null>(null)
  useEffect(() => () => { active.current?.abort(); active.current = null; setBusy(false) }, [token])

  async function request(action: Action) {
    if (active.current || !editorRef.current || !ready) return
    const controller = new AbortController()
    active.current = controller
    setBusy(true); setError(''); setResult(null)
    try {
      const target = editorRef.current.capture(action)
      if (!target.text.trim()) throw new Error('Add text first; place the cursor after it for a continuation.')
      const response = await writingClient.getLLMAnswer({ documentId, requestId: crypto.randomUUID(),
        action, text: target.text, context: target.context, sourceRevision: target.revision },
        { headers: { authorization: `Bearer ${token}` }, timeoutMs: 50000, signal: controller.signal })
      if (active.current === controller) setResult({ target, answer: response.answer })
    } catch (error) {
      if (active.current === controller) setError(controller.signal.aborted ? 'Request cancelled.' : String(error))
    } finally {
      if (active.current === controller) { active.current = null; setBusy(false) }
    }
  }

  const suggestAfterPause = useEffectEvent(() => { void request(Action.SUGGEST) })
  useEffect(() => {
    if (!auto || !ready || busy || !lastTyped || lastTyped === lastSuggested.current) return
    const timer = setTimeout(() => {
      lastSuggested.current = lastTyped
      suggestAfterPause()
    }, 1500)
    return () => clearTimeout(timer)
  }, [auto, ready, busy, lastTyped])

  const stale = !!result && (!ready || result.target.token !== token ||
    result.target.version !== version || result.target.revision !== revision)
  function apply() {
    if (!result || stale || !editorRef.current) return
    try { editorRef.current.apply(result.target, result.answer); setResult(null) }
    catch (error) { setError(String(error)) }
  }

  return <aside className="writing-panel" aria-label="Writing assistant">
    <h3>Writing assistant</h3>
    <p>Select text for grammar or enhancement. Continue uses text before the cursor. Summaries use the selection or whole note.</p>
    <div className="writing-actions">
      {[[Action.GRAMMAR, 'Fix grammar'], [Action.SUGGEST, 'Continue'], [Action.SUMMARIZE, 'Summarize'], [Action.ENHANCE, 'Enhance']].map(([action, label]) =>
        <button key={action} disabled={busy || !ready || !token} onClick={() => void request(action as Action)}>{label}</button>)}
    </div>
    <label><input type="checkbox" checked={auto} onChange={event => setAuto(event.target.checked)} /> Suggest after typing pauses</label>
    {busy && <p role="status">Thinking locally… <button onClick={() => active.current?.abort()}>Cancel</button></p>}
    {error && <p role="alert">{error}</p>}
    {result && <div className="ai-result"><h4>Preview</h4><pre>{result.answer}</pre>
      {stale && <p>Document or selection changed. Request a fresh result.</p>}
      {result.target.action !== Action.SUMMARIZE && <button disabled={stale} onClick={apply}>Apply to document</button>}
      <button onClick={() => setResult(null)}>Dismiss</button>
    </div>}
    <small>Qwen runs locally. Review its output; summaries are displayed only.</small>
  </aside>
}
