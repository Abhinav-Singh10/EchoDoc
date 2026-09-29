import { useEffect, useRef, useState } from "react";
import { Compartment, EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { yCollab, yUndoManagerKeymap } from "y-codemirror.next";
import * as Y from "yjs";
import { documentClient } from "./rpc";
import type { Presence } from "./gen/collab/document/v1/document_pb";

type Props = {
  documentId: string;
  title: string;
  token: string;
};

export default function DocumentPreview({ documentId, title, token }: Props) {
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
    const doc = new Y.Doc();
    const text = doc.getText("content");

    const remoteOrigin = Symbol("server");
    const editing = new Compartment();

    const pending: {
      requestId: string;
      update: Uint8Array;
    }[] = [];

    let sending = false;
    let stopped = false;
    let streamConnected = false;
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

          await documentClient.submitUpdate(
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

          pending.shift();
          setPendingCount(pending.length);
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
      void sendPresence();
      pending.push({
        requestId: crypto.randomUUID(),
        update,
      });

      setPendingCount(pending.length);
      void flushUpdates();
    }

    doc.on("update", onLocalUpdate);

    async function watch() {
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
          setRevision(event.revision);

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

    void watch();

    return () => {
      retrySave.current = null;
      reconnect.current = null;
      controller.abort();
      clearInterval(presenceTimer);
      doc.off("update", onLocalUpdate);
      editor.destroy();
      doc.destroy();
    };
  }, [documentId, token]);

  return (
    <article aria-label="Shared document editor">
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
          Received revision: {revision.toString()} —{" "}
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
      <div ref={element} />
    </article>
  );
}
