import { useState } from 'react'
import type { DocumentInfo } from './gen/collab/document/v1/document_pb'
import { documentClient } from './rpc'

import DocumentPreview from './DocumentPreview'

type Props = { token: string; pendingCount: number; onPendingChange: (count: number) => void }
export default function DocumentList({ token, pendingCount, onPendingChange }: Props) {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [title, setTitle] = useState('')

 const [selected, setSelected] = useState<DocumentInfo | null>(null)

  async function refresh() {
    setBusy(true)
    setError('')

    try {
      const response = await documentClient.listDocuments(
        {},
        {
          headers: {
            authorization: `Bearer ${token}`,
          },
          timeoutMs: 5000,
        },
      )

      setDocuments(response.documents)
    } catch {
      setError('Could not load documents. Check your connection and session.')
    } finally {
      setBusy(false)
    }
  }

  async function createDocument() {
    const trimmedTitle = title.trim()
    if (!trimmedTitle) return

    setBusy(true)
    setError('')

    try {
      await documentClient.createDocument(
        { title: trimmedTitle },
        {
          headers: {
            authorization: `Bearer ${token}`,
          },
          timeoutMs: 5000,
        },
      )

      setTitle('')
      await refresh()
    } catch {
      setError(
        'Creation was not confirmed. Refresh documents before trying again.',
      )
    } finally {
      setBusy(false)
    }
  }

  
  return (
    <section className="workspace">
      <aside className="document-sidebar">
      <h2>Documents</h2>
      <form
        onSubmit={event => {
          event.preventDefault()
          createDocument()
        }}
      >
        <fieldset disabled={busy || !token}>
          <legend>Create a document</legend>

          <label>
            Title
            <input
              value={title}
              onChange={event => setTitle(event.target.value)}
              required
            />
          </label>

          <button type="submit" disabled={!title.trim()}>
            Create document
          </button>
        </fieldset>
      </form>

      <button onClick={refresh} disabled={busy || !token}>
           {busy ? 'Working…' : 'Refresh documents'}
      </button>

      {error && <p role="alert">{error}</p>}
      {documents === null && <p>Refresh to load your documents.</p>}
      {documents?.length === 0 && <p>No documents yet.</p>}

      <ul>
        {documents?.map(document => (
          <li key={document.documentId}>
          <button
            type="button"
            onClick={() => { if (!pendingCount) setSelected(document) }}
            disabled={busy || !token || pendingCount > 0}
          >
            {document.title}
          </button>
          {' '}— revision {document.revision.toString()}
        </li>
        ))}
      </ul>
      {pendingCount > 0 && <p>Wait for Saved before switching documents or logging out.</p>}
      </aside>
      <div className="document-main">
      {!selected && <p className="empty-state">Create or open a document to begin collaborating.</p>}
      {selected && (
        <>
          <button type="button" disabled={pendingCount > 0} onClick={() => setSelected(null)}>
            Close preview
          </button>

          <DocumentPreview
            key={selected.documentId}
            documentId={selected.documentId}
            title={selected.title}
            token={token}
            onPendingChange={onPendingChange}
          />
        </>
      )}
      </div>
    </section>
  )
}