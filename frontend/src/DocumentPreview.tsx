import { useEffect, useRef, useState } from "react";
import { Compartment, EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";
import { defaultKeymap } from "@codemirror/commands";
import { yCollab, yUndoManagerKeymap } from "y-codemirror.next";
import * as Y from "yjs";
import { documentClient } from "./rpc";

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
            "Saving was not confirmed. Copy your text before closing.",
          );
        }
      } finally {
        sending = false;
      }
    }

    function onLocalUpdate(update: Uint8Array, origin: unknown) {
      if (origin === remoteOrigin || controller.signal.aborted) return;

      pending.push({
        requestId: crypto.randomUUID(),
        update,
      });

      setPendingCount(pending.length);
      void flushUpdates();
    }

    doc.on("update", onLocalUpdate);

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
        );

        for await (const event of stream) {
          if (controller.signal.aborted) return;

          Y.applyUpdate(doc, event.update, remoteOrigin);
          setRevision(event.revision);

          if (event.kind === "snapshot" && !stopped) {
            editor.dispatch({
              effects: editing.reconfigure(editingExtensions(true)),
            });
          }
        }

        if (!controller.signal.aborted) {
          stopEditing(
            "Stream ended. Copy any unconfirmed text before closing.",
          );
        }
      } catch {
        if (!controller.signal.aborted) {
          stopEditing(
            "Stream disconnected. Copy any unconfirmed text before closing.",
          );
        }
      }
    }

    void watch();

    return () => {
      controller.abort();
      doc.off("update", onLocalUpdate);
      editor.destroy();
      doc.destroy();
    };
  }, [documentId, token]);

  return (
    <article aria-label="Shared document editor">
      <h3>{title}</h3>

      {error && <p role="alert">{error}</p>}
      {revision === null && !error && <p>Connecting…</p>}

      {revision !== null && (
        <p>
          Received revision: {revision.toString()} —{" "}
          {error
            ? `Editing paused; ${pendingCount} unconfirmed update(s)`
            : pendingCount > 0
              ? `Saving ${pendingCount} update(s)…`
              : "Saved"}
        </p>
      )}

      <div ref={element} />
    </article>
  );
}
