import { useCallback, useEffect, useRef, useState } from "react";
import type { DocumentVersionInfo } from "./gen/collab/document/v1/document_pb";
import { documentClient } from "./rpc";
import { retryRead } from "./recovery";
import { versionText } from "./history";

type Props = { documentId: string; token: string };

function HistoryContents({ documentId, token }: Props) {
  const [versions, setVersions] = useState<DocumentVersionInfo[]>([]);
  const [loadedThrough, setLoadedThrough] = useState<bigint | null>(null);
  const [oldest, setOldest] = useState(0n);
  const [nextBefore, setNextBefore] = useState<bigint | undefined>();
  const [busy, setBusy] = useState(true);
  const [listError, setListError] = useState("");
  const [selected, setSelected] = useState<bigint | null>(null);
  const [preview, setPreview] = useState<{ revision: bigint; text: string } | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const listRequest = useRef<AbortController | null>(null);
  const previewRequest = useRef<AbortController | null>(null);

  const loadPage = useCallback(async (before?: bigint) => {
    listRequest.current?.abort();
    const request = new AbortController();
    listRequest.current = request;
    setBusy(true);
    setListError("");
    try {
      const response = await retryRead(timeoutMs => documentClient.listDocumentVersions(
        { documentId, beforeRevision: before },
        { headers: { authorization: `Bearer ${token}` }, signal: request.signal, timeoutMs },
      ), request.signal);
      if (request.signal.aborted || listRequest.current !== request) return;
      if (before === undefined) {
        setVersions(response.versions);
        setLoadedThrough(response.currentRevision);
        setOldest(response.oldestAvailableRevision);
      } else {
        setVersions(current => {
          const seen = new Set(current.map(version => version.revision));
          return [...current, ...response.versions.filter(version => !seen.has(version.revision))];
        });
      }
      setNextBefore(response.nextBeforeRevision);
    } catch {
      if (!request.signal.aborted && listRequest.current === request)
        setListError("History is unavailable. Check your connection and session, then refresh history.");
    } finally {
      if (!request.signal.aborted && listRequest.current === request) setBusy(false);
    }
  }, [documentId, token]);

  useEffect(() => {
    const lifetime = new AbortController();
    void Promise.resolve().then(() => {
      if (!lifetime.signal.aborted) void loadPage();
    });
    return () => {
      lifetime.abort();
      listRequest.current?.abort();
      previewRequest.current?.abort();
    };
  }, [loadPage]);

  async function selectVersion(revision: bigint) {
    previewRequest.current?.abort();
    const request = new AbortController();
    previewRequest.current = request;
    setSelected(revision);
    setPreview(null);
    setPreviewBusy(true);
    setPreviewError("");
    try {
      const response = await retryRead(timeoutMs => documentClient.getDocumentVersion(
        { documentId, revision },
        { headers: { authorization: `Bearer ${token}` }, signal: request.signal, timeoutMs },
      ), request.signal);
      if (request.signal.aborted || previewRequest.current !== request) return;
      if (response.document?.revision !== revision) throw new Error("Unexpected revision");
      setPreview({ revision, text: versionText(response.state) });
    } catch {
      if (!request.signal.aborted && previewRequest.current === request)
        setPreviewError("Could not load this saved version. Select it again to retry.");
    } finally {
      if (!request.signal.aborted && previewRequest.current === request) setPreviewBusy(false);
    }
  }

  return (
    <div>
      <p>Saved revisions only. Select a revision for a read-only preview.</p>
      {loadedThrough !== null && <p>History loaded through revision {loadedThrough.toString()}. Refresh to include newer edits.</p>}
      {oldest > 0n && <p>History is available from revision {oldest.toString()}, the saved baseline for this older document.</p>}
      <button type="button" disabled={busy} onClick={() => void loadPage()}>Refresh history</button>
      {busy && <p role="status">Loading history…</p>}
      {listError && <p role="alert">{listError}</p>}
      <div className="history-layout">
        <div>
          <ul className="version-list" aria-label="Saved revisions">
            {versions.map(version => (
              <li key={version.revision.toString()}>
                <button type="button" aria-pressed={selected === version.revision}
                  onClick={() => void selectVersion(version.revision)}>
                  Revision {version.revision.toString()}
                  <small>{version.revision === 0n ? "Initial version" :
                    version.authorUsername || version.authorId || "Existing baseline"}</small>
                </button>
              </li>
            ))}
          </ul>
          {!busy && !listError && versions.length === 0 && <p>No saved revisions available.</p>}
          {nextBefore !== undefined && <button type="button" disabled={busy}
            onClick={() => void loadPage(nextBefore)}>Load older</button>}
        </div>
        <section aria-label="Historical version preview">
          {selected === null && <p>Select a saved revision to preview it.</p>}
          {selected !== null && <h4>Read-only preview — revision {selected.toString()}</h4>}
          {previewBusy && <p role="status">Loading saved version…</p>}
          {previewError && <p role="alert">{previewError}</p>}
          {preview && (preview.text ? <pre className="version-preview">{preview.text}</pre> : <p>This revision is empty.</p>)}
        </section>
      </div>
    </div>
  );
}

export default function HistoryPanel({ documentId, token }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <section className="version-history" aria-label="Document version history">
      <button type="button" disabled={!token} aria-expanded={open} onClick={() => setOpen(value => !value)}>
        {open ? "Close version history" : "Version history"}
      </button>
      {open && token && <HistoryContents key={`${documentId}:${token}`} documentId={documentId} token={token} />}
    </section>
  );
}
