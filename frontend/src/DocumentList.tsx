import { useState } from 'react'
import type { DocumentInfo } from './gen/collab/document/v1/document_pb'
import { documentClient } from './rpc'

export default function DocumentList({ token }: { token: string }) {
  const [documents, setDocuments] = useState<DocumentInfo[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

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

  return (
    <section>
      <h2>Documents</h2>

      <button onClick={refresh} disabled={busy}>
        {busy ? 'Loading…' : 'Refresh documents'}
      </button>

      {error && <p role="alert">{error}</p>}
      {documents === null && <p>Refresh to load your documents.</p>}
      {documents?.length === 0 && <p>No documents yet.</p>}

      <ul>
        {documents?.map(document => (
          <li key={document.documentId}>
            {document.title} — revision {document.revision.toString()}
          </li>
        ))}
      </ul>
    </section>
  )
}