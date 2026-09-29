import { useState } from 'react'
import type { DocumentInfo } from './gen/collab/document/v1/document_pb'
import { documentClient } from './rpc'

import DocumentPreview from './DocumentPreview'

export default function DocumentList({ token }: { token: string }) {
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
    <section>
      <h2>Documents</h2>
      <form
        onSubmit={event => {
          event.preventDefault()
          createDocument()
        }}
      >
        <fieldset disabled={busy}>
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

      <button onClick={refresh} disabled={busy}>
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
            onClick={() => setSelected(document)}
            disabled={busy}
          >
            {document.title}
          </button>
          {' '}— revision {document.revision.toString()}
        </li>
        ))}
      </ul>
      {selected && (
        <>
          <button type="button" onClick={() => setSelected(null)}>
            Close preview
          </button>

          <DocumentPreview
            key={selected.documentId}
            documentId={selected.documentId}
            title={selected.title}
            token={token}
          />
        </>
      )}
    </section>
  )
}