import { useEffect, useState } from 'react'
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
  const [preview, setPreview] = useState<{
    text: string
    revision: bigint
  } | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const doc = new Y.Doc()
    const text = doc.getText('content')

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

          setPreview({
            text: text.toString(),
            revision: event.revision,
          })
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
      doc.destroy()
    }
  }, [documentId, token])

  return (
    <article aria-label="Live document preview">
      <h3>{title}</h3>

      {error && <p role="alert">{error}</p>}
      {!preview && !error && <p>Connecting…</p>}

      {preview && (
        <>
          <p>
            {error ? 'Last received' : 'Live'} revision:{' '}
            {preview.revision.toString()} — read-only
          </p>

          <div style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>
            {preview.text || 'This document is empty.'}
          </div>
        </>
      )}
    </article>
  )
}