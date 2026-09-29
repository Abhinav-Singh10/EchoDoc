import { useEffect, useRef, useState } from 'react'
import { EditorState } from '@codemirror/state'
import { EditorView, lineNumbers } from '@codemirror/view'
import { yCollab } from 'y-codemirror.next'
import * as Y from 'yjs'
import { documentClient } from './rpc'

type Props = {
  documentId: string
  title: string
  token: string
}

export default function DocumentPreview({
  documentId,
  title,
  token,
}: Props) {
  const element = useRef<HTMLDivElement>(null)
  const [revision, setRevision] = useState<bigint | null>(null)
  const [error, setError] = useState('')
  

  useEffect(() => {
    const controller = new AbortController()
    const doc = new Y.Doc()
    const text = doc.getText('content')

    const editor = new EditorView({
      parent: element.current!,
      state: EditorState.create({
        doc: text.toString(),
        extensions: [
          lineNumbers(),
          EditorView.lineWrapping,
          yCollab(text, null),
          EditorState.readOnly.of(true),
          EditorView.editable.of(false),
          EditorView.contentAttributes.of({
            'aria-label': 'Shared document',
          }),
          EditorView.theme({
            '&': { border: '1px solid #888' },
            '.cm-content': { minHeight: '200px' },
          }),
        ],
      }),
    })

    async function watch() {
      try {
        const stream = documentClient.watchDocument(
          {
            documentId,
            connectionId: crypto.randomUUID(),
          },
          {
            headers: {
              authorization: `Bearer ${token}`,
            },
            signal: controller.signal,
          },
        )

        for await (const event of stream) {
          if (controller.signal.aborted) return

          Y.applyUpdate(doc, event.update)

          setRevision(event.revision)
        }

        if (!controller.signal.aborted) {
          setError('Stream ended. Close and reopen the document.')
        }
      } catch {
        if (!controller.signal.aborted) {
          setError('Stream disconnected. Close and reopen the document.')
        }
      }
    }

    void watch()

    return () => {
      controller.abort()
      editor.destroy()
      doc.destroy()
    }
  }, [documentId, token])

  return (
    <article aria-label="Live document preview">
      <h3>{title}</h3>

      {error && <p role="alert">{error}</p>}
      {revision === null && !error && <p>Connecting…</p>}

      {revision !== null && (
        <p>
          {error ? 'Last received' : 'Live'} revision:{' '}
          {revision.toString()} — read-only
        </p>
      )}

      <div ref={element} />
    </article>
  )
}