import * as Y from "yjs";
import { writeFileSync } from "node:fs";

const doc = new Y.Doc();
const text = doc.getText("content");

text.insert(0, "Hello 👋");

const update = Y.encodeStateAsUpdate(doc);

const output = new URL(
  "../../scratch/crdt/javascript.bin",
  import.meta.url,
);

writeFileSync(output, update);

console.log("JavaScript text:", text.toString());
console.log("Update size:", update.length, "bytes");