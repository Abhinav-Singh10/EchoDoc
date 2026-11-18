import { useEffect, useRef, useState } from 'react'
import type { DocumentInfo } from './gen/collab/document/v1/document_pb'
import { documentClient } from './rpc'
import DocumentPreview from './DocumentPreview'
import HistoryPanel from './HistoryPanel'
import { retryRead } from './recovery'

type Props = {
  token: string
  pendingCount: number
  onPendingChange: (count: number) => void
}

export default function DocumentList({ token, pendingCount, onPendingChange }: Props) {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [title, setTitle] = useState('')
  const [selectedDocument, setSelectedDocument] = useState<DocumentInfo | null>(null)
  const reads = useRef(new AbortController())

  useEffect(() => {
    const controller = new AbortController()
    reads.current = controller
    return () => controller.abort()
  }, [token])

  async function refreshDocuments() {
    setBusy(true)
    setError('')
    const signal = reads.current.signal
    try {
      const response = await retryRead(timeoutMs => documentClient.listDocuments(
        {},
        { headers: { authorization: `Bearer ${token}` }, timeoutMs, signal },
      ), signal)
      if (!signal.aborted) setDocuments(response.documents)
    } catch {
      if (!signal.aborted) setError('Could not load documents. Check your connection and session.')
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
        { headers: { authorization: `Bearer ${token}` }, timeoutMs: 5000 },
      )
      setTitle('')
      await refreshDocuments()
    } catch {
      setError('Creation was not confirmed. Refresh documents before trying again.')
    } finally {
      setBusy(false)
    }
  }

  function openDocument(document: DocumentInfo) {
    if (!pendingCount) setSelectedDocument(document)
  }

  return (
    <section className="workspace">
      <div className="document-sidebar-column">
        <aside className="document-sidebar">
          <h2>Documents</h2>
          <form onSubmit={event => { event.preventDefault(); void createDocument() }}>
            <fieldset disabled={busy || !token}>
              <legend>Create a document</legend>
              <label>
                Title
                <input value={title} onChange={event => setTitle(event.target.value)} required />
              </label>
              <button type="submit" disabled={!title.trim()}>Create document</button>
            </fieldset>
          </form>

          <button onClick={refreshDocuments} disabled={busy || !token}>
            {busy ? 'Working...' : 'Refresh documents'}
          </button>
          {error && <p role="alert">{error}</p>}
          {documents === null && <p>Refresh to load your documents.</p>}
          {documents?.length === 0 && <p>No documents yet.</p>}

          <ul>
            {documents?.map(document => (
              <li key={document.documentId}>
                <button
                  type="button"
                  onClick={() => openDocument(document)}
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

        {selectedDocument ? (
          <HistoryPanel
            key={selectedDocument.documentId}
            documentId={selectedDocument.documentId}
            title={selectedDocument.title}
            token={token}
          />
        ) : (
          <section className="version-history" aria-label="Document version history">
            <h2>Version history</h2>
            <p>Open a document to view its saved revisions.</p>
          </section>
        )}
      </div>

      <div className="document-main">
        {!selectedDocument && <p className="empty-state">Create or open a document to begin collaborating.</p>}
        {selectedDocument && (
          <>
            <button type="button" disabled={pendingCount > 0} onClick={() => setSelectedDocument(null)}>
              Close preview
            </button>
            <DocumentPreview
              key={selectedDocument.documentId}
              documentId={selectedDocument.documentId}
              title={selectedDocument.title}
              token={token}
              onPendingChange={onPendingChange}
            />
          </>
        )}
      </div>
    </section>
  )
}
