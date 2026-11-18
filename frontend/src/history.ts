import * as Y from "yjs";

export function versionText(state: Uint8Array): string {
  const preview = new Y.Doc();
  try {
    Y.applyUpdate(preview, state);
    return preview.getText("content").toString();
  } finally {
    preview.destroy();
  }
}
