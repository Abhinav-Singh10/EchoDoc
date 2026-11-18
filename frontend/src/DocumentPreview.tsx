import { useEffect, useRef, useState } from "react";
import { Compartment, EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { yCollab, yUndoManagerKeymap } from "y-codemirror.next";
import * as Y from "yjs";
import { documentClient } from "./rpc";
import { Code, ConnectError } from "@connectrpc/connect";
import { backoff, pause, retryable } from "./recovery";
import { Action } from "./gen/collab/ai/v1/ai_pb";
import WritingPanel from "./WritingPanel";
import HistoryPanel from "./HistoryPanel";
import type { WritingEditor } from "./writing";
import type { Presence } from "./gen/collab/document/v1/document_pb";

type Props = {
  documentId: string;
  title: string;
  token: string;
  onPendingChange: (count: number) => void;
};

export default function DocumentPreview({
  documentId,
  title,
  token,
  onPendingChange,
}: Props) {
  const [local] = useState(() => ({
    doc: new Y.Doc(),
    version:0,
    pending: [] as { requestId: string; update: Uint8Array }[],
  }));
  const [lastTyped, setLastTyped] = useState(0);
  const [editVersion, setEditVersion] = useState(0);
  const writingRef = useRef<WritingEditor | null>(null);
  const element = useRef<HTMLDivElement>(null);
  const [revision, setRevision] = useState<bigint | null>(null);
  const [error, setError] = useState("");
  const [pendingCount, setPendingCount] = useState(0);
  const [connected, setConnected] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const retrySave = useRef<(() => Promise<void>) | null>(null);
  const [connecting, setConnecting] = useState(true);
  const reconnect = useRef<(() => void) | null>(null);
  const [presenceError, setPresenceError] = useState("");
  const [users, setUsers] = useState<Presence[]>([]);
  const [streamServer, setStreamServer] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const doc = local.doc;
    const text = doc.getText("content");

    const remoteOrigin = Symbol("server");
    const editing = new Compartment();

    const pending = local.pending;

    let sending: Promise<void> | null = null;
    let stopped = true;
    let streamConnected = false;
    let latestRevision = 0n;
    let version = local.version;
    let watching = false;
    let attempt: AbortController | null = null;
    let saveError: unknown;
    let manualRestart = false;
    let connectionId = "";
    let streamServerId = "";
    let lastEdit = 0;
    let lastPresence: boolean | null = null;
    let presenceSending = false;

    async function sendPresence() {
      const active = Date.now() - lastEdit < 3000;
      if (!streamConnected || presenceSending || lastPresence === active)
        return;
      const current = attempt;
      presenceSending = true;
      try {
        await documentClient.updatePresence(
          { documentId, connectionId, streamServerId, editing: active },
          {
            headers: { authorization: `Bearer ${token}` },
            timeoutMs: 5000,
            signal: current?.signal,
          },
        );
        if (!controller.signal.aborted && current === attempt && !current?.signal.aborted) {
          lastPresence = active;
          setPresenceError("");
        }
      } catch {
        if (!controller.signal.aborted && current === attempt && !current?.signal.aborted)
          setPresenceError("Could not update editing status.");
      } finally {
        presenceSending = false;
      }
    }
    const presenceTimer = setInterval(() => void sendPresence(), 1000);

    function editingExtensions(enabled: boolean) {
      return [
        EditorState.readOnly.of(!enabled),
        EditorView.editable.of(enabled),
        keymap.of(enabled ? [...yUndoManagerKeymap, ...defaultKeymap] : []),
      ];
    }

    const editor = new EditorView({
      parent: element.current!,
      state: EditorState.create({
        doc: text.toString(),
        extensions: [
          EditorView.updateListener.of((update) => {
            if (update.docChanged || update.selectionSet) {
              local.version = ++version;
              setEditVersion(version);
            }
          }),
          lineNumbers(),
          EditorView.lineWrapping,
          yCollab(text, null),
          editing.of(editingExtensions(false)),
          EditorView.contentAttributes.of({
            "aria-label": "Shared document",
          }),
          EditorView.theme({
            "&": { border: "1px solid #888" },
            ".cm-content": { minHeight: "200px" },
          }),
        ],
      }),
    });

    writingRef.current = {
      capture(action) {
        if (!streamConnected || stopped || pending.length)
          throw new Error("Wait for Saved first.");
        const { from, to } = editor.state.selection.main;
        const full = editor.state.doc.toString();
        if (action === Action.SUGGEST && from !== to) throw new Error("Place the cursor where the continuation should start.");
        if (
          (action === Action.GRAMMAR || action === Action.ENHANCE) &&
          from === to
        ) {
          throw new Error("Select a passage first.");
        }
        return {
          action,
          from,
          to,
          version,
          revision: latestRevision,
          token,
          text:
            action === Action.SUGGEST
              ? full.slice(0, from)
              : from === to
                ? full
                : full.slice(from, to),
          context: action === Action.SUGGEST ? full.slice(to) : "",
        };
      },
      apply(target, answer) {
        const current = editor.state.selection.main;
        if (!streamConnected || stopped || pending.length || target.token !== token ||
            target.revision !== latestRevision || target.version !== version ||
            target.from !== current.from || target.to !== current.to) {
          throw new Error("Document or selection changed. Request a fresh result.");
        }
        if (target.action === Action.SUMMARIZE) return;
        let insert = answer;
        if (target.action === Action.SUGGEST && target.from > 0 &&
            !/\s$/.test(editor.state.doc.sliceString(0, target.from)) && !/^\s/.test(insert)) insert = " " + insert;
        editor.dispatch({ changes: { from: target.from, to: target.to, insert },
          selection: { anchor: target.from + insert.length }, userEvent: "input.ai" });
        editor.focus();
      },
    };

    function stopEditing(message: string) {
      stopped = true;
      setError(message);

      editor.dispatch({
        effects: editing.reconfigure(editingExtensions(false)),
      });
    }

    function flushUpdates(): Promise<void> {
      if (sending) return sending;
      const current = attempt;
      if (!streamConnected || !current || current.signal.aborted) return Promise.resolve();
      sending = (async () => {
        while (pending.length > 0 && !current.signal.aborted) {
          const next = pending[0];

          const response = await documentClient.submitUpdate(
            {
              documentId,
              requestId: next.requestId,
              update: next.update,
            },
            {
              headers: {
                authorization: `Bearer ${token}`,
              },
              timeoutMs: 5000,
              signal: current.signal,
            },
          );

          if (controller.signal.aborted || current.signal.aborted || current !== attempt) return;

          latestRevision =
            response.revision > latestRevision
              ? response.revision
              : latestRevision;
          setRevision(latestRevision);

          pending.shift();
          setPendingCount(pending.length);
          onPendingChange(pending.length);
        }
      })().finally(() => {
        sending = null;
      });
      return sending;
    }

    function onLocalUpdate(update: Uint8Array, origin: unknown) {
      if (origin === remoteOrigin || controller.signal.aborted) return;

      lastEdit = Date.now();
      setLastTyped(lastEdit);
      void sendPresence();
      pending.push({
        requestId: crypto.randomUUID(),
        update,
      });

      setPendingCount(pending.length);
      onPendingChange(pending.length);
      const current = attempt;
      void flushUpdates().catch((error: unknown) => {
        if (controller.signal.aborted || current !== attempt || current?.signal.aborted) return;
        saveError = error;
        stopEditing("Saving was not confirmed. Recovering the connection…");
        current?.abort();
      });
    }

    doc.on("update", onLocalUpdate);

    async function watch() {
      if (watching || controller.signal.aborted) return;
      watching = true;
      let failures = 0;
      // Defer initial React state updates until after effect setup.
      await Promise.resolve();
      if (!token) {
        if (!controller.signal.aborted) {
          stopEditing("Log in again as the same user to recover pending edits.");
          setConnecting(false);
          setConnected(false);
          setStreamServer("");
        }
        watching = false;
        return;
      }
      try {
        while (!controller.signal.aborted) {
          attempt = new AbortController();
          const current = attempt;
          saveError = undefined;
          manualRestart = false;
          streamConnected = false;
          connectionId = crypto.randomUUID();
          streamServerId = "";
          lastPresence = null;
          setStreamServer("");
          setConnected(false);
          setUsers([]);
          setConnecting(true);
          stopEditing("Connecting; pending edits are kept in this tab…");
          let failure: unknown;
          let lastEvent = performance.now();
          const watchdog = setInterval(() => {
            if (performance.now() - lastEvent >= 6000 && !current.signal.aborted) {
              saveError = new ConnectError("Document stream stopped responding", Code.Unavailable);
              stopEditing("Document stream stopped responding. Reconnecting…");
              current.abort();
            }
          }, 250);
          try {
            const stream = documentClient.watchDocument(
              { documentId, connectionId },
              { headers: { authorization: `Bearer ${token}` }, signal: current.signal },
            );
            for await (const event of stream) {
              if (controller.signal.aborted || current.signal.aborted) break;
              lastEvent = performance.now();
              if (event.kind === "presence") {
                setUsers(event.users);
                continue;
              }
              if (event.kind !== "snapshot" && event.kind !== "update") continue;
              Y.applyUpdate(doc, event.update, remoteOrigin);
              latestRevision = event.revision > latestRevision ? event.revision : latestRevision;
              setRevision(latestRevision);
              if (event.kind === "snapshot") {
                streamServerId = event.streamServerId;
                setStreamServer(streamServerId);
                streamConnected = true;
                setConnected(true);
                setRetrying(pending.length > 0);
                await flushUpdates();
                if (controller.signal.aborted || current.signal.aborted) break;
                stopped = false;
                setError("");
                setConnecting(false);
                setRetrying(false);
                failures = 0;
                editor.dispatch({ effects: editing.reconfigure(editingExtensions(true)) });
                void sendPresence();
              }
            }
            failure = new ConnectError("Document stream ended", Code.Unavailable);
          } catch (error) {
            failure = error;
          } finally {
            clearInterval(watchdog);
            current.abort();
            streamConnected = false;
            if (!controller.signal.aborted) {
              setConnected(false);
              setConnecting(true);
              stopEditing("Connection lost. Recovering; pending edits are kept in this tab…");
            }
            // Drain the previous save before another attempt can send one.
            try { await sending; } catch { /* Retain the pending update for recovery. */ }
          }
          if (controller.signal.aborted) return;
          setConnected(false);
          setUsers([]);
          setStreamServer("");
          setRetrying(false);
          failure = saveError ?? failure;
          if (!manualRestart && !retryable(failure)) {
            const unauthenticated = failure instanceof ConnectError && failure.code === Code.Unauthenticated;
            stopEditing(unauthenticated
              ? "Session invalid. Log in again as the same user; pending edits are kept in this tab."
              : `Recovery stopped: ${ConnectError.from(failure).rawMessage}. Copy your text before closing.`);
            return;
          }
          stopEditing("Connection lost. Reconnecting automatically; pending edits are kept in this tab…");
          if (!manualRestart) await pause(backoff(failures++), controller.signal);
        }
      } catch {
        // The only outer rejection is cancellation of the backoff on cleanup.
      } finally {
        watching = false;
        if (!controller.signal.aborted) setConnecting(false);
      }
    }

    function restart() {
      if (controller.signal.aborted) return;
      if (watching) {
        manualRestart = true;
        attempt?.abort();
      } else void watch();
    }
    retrySave.current = async () => restart();
    reconnect.current = restart;

    function warnBeforeLeaving(event: BeforeUnloadEvent) {
      if (pending.length) {
        event.preventDefault();
        event.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", warnBeforeLeaving);
    void watch();

    return () => {
      window.removeEventListener("beforeunload", warnBeforeLeaving);
      writingRef.current = null;
      retrySave.current = null;
      reconnect.current = null;
      controller.abort();
      attempt?.abort();
      clearInterval(presenceTimer);
      doc.off("update", onLocalUpdate);
      editor.destroy();
    };
  }, [documentId, token, onPendingChange, local]);

  return (
    <article aria-label="Shared document editor" className="editor-panel">
      <h3>{title}</h3>

      {error && <p role="alert">{error}</p>}
      {pendingCount > 0 && (error || retrying) && (
        <button
          type="button"
          disabled={retrying || connecting || !token}
          onClick={() => {
            void retrySave.current?.();
          }}
        >
          {retrying ? "Retrying…" : "Retry save"}
        </button>
      )}
      {!connected && (
        <button
          type="button"
          disabled={connecting}
          onClick={() => reconnect.current?.()}
        >
          {connecting ? "Connecting…" : "Reconnect"}
        </button>
      )}

      {revision !== null && (
        <p>
          Document revision: {revision.toString()} —{" "}
          {connecting
            ? "Reconnecting…"
            : error
              ? `Editing paused; ${pendingCount} unconfirmed update(s)`
              : pendingCount > 0
                ? `Saving ${pendingCount} update(s)…`
                : "Saved"}
        </p>
      )}
      {presenceError && <p role="alert">{presenceError}</p>}
      {connected && (
        <div>
          <p>Document stream backend: {streamServer || "unknown"}</p>
          <p>Open connections on this backend, including this tab: {users.length}</p>

          <ul>
            {users.map((user) => (
              <li key={user.connectionId}>
                {user.username} — {user.editing ? "editing" : "viewing"}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="editor-columns"><div ref={element} />
      <WritingPanel
        editorRef={writingRef}
        documentId={documentId}
        token={token}
        ready={connected && !connecting && !error && pendingCount === 0} 
        version={editVersion} revision={revision} lastTyped={lastTyped} />
        </div>
      <HistoryPanel documentId={documentId} token={token} />
    </article>
  );
}
