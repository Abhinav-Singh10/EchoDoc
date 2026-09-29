import { useEffect, useRef, useState } from "react";
import { Compartment, EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { yCollab, yUndoManagerKeymap } from "y-codemirror.next";
import * as Y from "yjs";
import { documentClient } from "./rpc";
import { Action } from "./gen/collab/ai/v1/ai_pb";
import WritingPanel from "./WritingPanel";
import type { WritingEditor } from "./writing";
import type { Presence } from "./gen/collab/document/v1/document_pb";

type Props = {
  documentId: string;
  title: string;
  token: string;
  onPendingChange: (count: number) => void;
};

export default function DocumentPreview({ documentId, title, token, onPendingChange }: Props) {
  const [local] = useState(() => ({
    doc: new Y.Doc(),
    version: 0,
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

  useEffect(() => {
    const controller = new AbortController();
    const doc = local.doc;
    const text = doc.getText("content");

    const remoteOrigin = Symbol("server");
    const editing = new Compartment();

    const pending = local.pending;

    let sending = false;
    let stopped = false;
    let streamConnected = false;
    let latestRevision = 0n;
    let version = local.version;
    let watching = false;
    let connectionId = "";
    let lastEdit = 0;
    let lastPresence: boolean | null = null;
    let presenceSending = false;

    async function sendPresence() {
      const active = Date.now() - lastEdit < 3000;
      if (!streamConnected || presenceSending || lastPresence === active) return;
      presenceSending = true;
      try {
        await documentClient.updatePresence({ documentId, connectionId, editing: active }, {
          headers: { authorization: `Bearer ${token}` }, timeoutMs: 5000,
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          lastPresence = active;
          setPresenceError("");
        }
      } catch {
        if (!controller.signal.aborted) setPresenceError("Could not update editing status.");
      } finally { presenceSending = false; }
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
          EditorView.updateListener.of(update => {
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
        if (!streamConnected || stopped || pending.length) throw new Error("Wait for Saved first.");
        const { from, to } = editor.state.selection.main;
        const full = editor.state.doc.toString();
        if (action === Action.SUGGEST && from !== to) throw new Error("Place the cursor where the continuation should start.");
        if ((action === Action.GRAMMAR || action === Action.ENHANCE) && from === to) {
          throw new Error("Select a passage first.");
        }
        return { action, from, to, version, revision: latestRevision, token,
          text: action === Action.SUGGEST ? full.slice(0, from) : from === to ? full : full.slice(from, to),
          context: action === Action.SUGGEST ? full.slice(to) : "" };
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

    async function flushUpdates() {
      if (sending || stopped || controller.signal.aborted) return;

      sending = true;

      try {
        while (pending.length > 0 && !stopped && !controller.signal.aborted) {
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
              signal: controller.signal,
            },
          );

          if (controller.signal.aborted) return;

          latestRevision = response.revision > latestRevision ? response.revision : latestRevision;
          setRevision(latestRevision);
          pending.shift();
          setPendingCount(pending.length);
          onPendingChange(pending.length);
        }
      } catch {
        if (!controller.signal.aborted) {
          stopEditing(
            "Saving was not confirmed. Retry if connected, or copy your text before closing.",
          );
        }
      } finally {
        sending = false;
      }
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
      void flushUpdates();
    }

    doc.on("update", onLocalUpdate);

    async function watch() {
      if (!token) {
        await Promise.resolve();
        if (!controller.signal.aborted) {
          stopEditing("Log in again as the same user to recover pending edits.");
          setConnecting(false);
        }
        return;
      }
      if (watching || controller.signal.aborted) return;

      watching = true;
      connectionId = crypto.randomUUID();
      lastPresence = null;

      try {
        const stream = documentClient.watchDocument(
          {
            documentId,
            connectionId,
          },
          {
            headers: {
              authorization: `Bearer ${token}`,
            },
            signal: controller.signal,
          },
        );

        for await (const event of stream) {
          if (controller.signal.aborted) return;

          if (event.kind === "presence") {
            setUsers(event.users);
            continue;
          }

          if (event.kind !== "snapshot" && event.kind !== "update") {
            continue;
          }

          Y.applyUpdate(doc, event.update, remoteOrigin);
          latestRevision = event.revision > latestRevision ? event.revision : latestRevision;
          setRevision(latestRevision);

          if (event.kind === "snapshot") {
            streamConnected = true;
            void sendPresence();
            setConnected(true);
            setConnecting(false);

            if (pending.length > 0) {
              stopEditing(
                "Connected again. Click Retry save to confirm pending edits.",
              );
            } else {
              stopped = false;
              setError("");

              editor.dispatch({
                effects: editing.reconfigure(editingExtensions(true)),
              });
            }
          }
        }

        if (!controller.signal.aborted) {
          streamConnected = false;
          setConnected(false);
          stopEditing("Stream ended. Restore the connection, then reconnect.");
        }
      } catch {
        if (!controller.signal.aborted) {
          streamConnected = false;
          setConnected(false);
          stopEditing(
            "Stream disconnected. Restore the connection, then reconnect.",
          );
        }
      } finally {
        watching = false;

        if (!controller.signal.aborted) {
          setConnecting(false);
        }
      }
    }

    retrySave.current = async () => {
      if (sending || !streamConnected || controller.signal.aborted) {
        return;
      }

      setRetrying(true);
      setError("");
      stopped = false;

      try {
        await flushUpdates();

        if (!stopped && !controller.signal.aborted) {
          editor.dispatch({
            effects: editing.reconfigure(editingExtensions(true)),
          });
        }
      } finally {
        if (!controller.signal.aborted) {
          setRetrying(false);
        }
      }
    };

    reconnect.current = () => {
      if (watching || controller.signal.aborted) return;

      if (sending) {
        setError(
          "A save request is still finishing. Try Reconnect again in a moment.",
        );
        return;
      }

      setError("");
      setConnecting(true);
      void watch();
    };

    function warnBeforeLeaving(event: BeforeUnloadEvent) {
      if (pending.length) { event.preventDefault(); event.returnValue = ""; }
    }
    window.addEventListener("beforeunload", warnBeforeLeaving);
    void watch();

    return () => {
      window.removeEventListener("beforeunload", warnBeforeLeaving);
      writingRef.current = null;
      retrySave.current = null;
      reconnect.current = null;
      controller.abort();
      clearInterval(presenceTimer);
      doc.off("update", onLocalUpdate);
      editor.destroy();
      // The component owns local.doc; changing a session only replaces the stream.
    };
  }, [documentId, token, onPendingChange, local]);

  return (
    <article aria-label="Shared document editor" className="editor-panel">
      <h3>{title}</h3>

      {error && <p role="alert">{error}</p>}
      {connected && pendingCount > 0 && (error || retrying) && (
        <button
          type="button"
          disabled={retrying}
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
      {presenceError && <p role="status">{presenceError}</p>}
      {connected && (
        <div>
          <p>Open connections, including this tab: {users.length}</p>

          <ul>
            {users.map((user) => (
              <li key={user.connectionId}>{user.username} — {user.editing ? "editing" : "viewing"}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="editor-columns"><div ref={element} />
      <WritingPanel editorRef={writingRef} documentId={documentId} token={token}
        ready={connected && !connecting && !error && pendingCount === 0}
        version={editVersion} revision={revision} lastTyped={lastTyped} />
      </div>
    </article>
  );
}
