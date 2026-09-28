import * as Y from "yjs";
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";

const folder = new URL("../../scratch/crdt/", import.meta.url);

const doc = new Y.Doc();
const text = doc.getText("content");

const original = readFileSync(new URL("javascript.bin", folder));
Y.applyUpdate(doc, original);

console.log("Before:", text.toString());

const update = readFileSync(new URL("python.bin", folder));
Y.applyUpdate(doc, update);

console.log("After:", text.toString());
assert.equal(text.toString(), "Hello 👋 from Python");

Y.applyUpdate(doc, update);

console.log("After duplicate:", text.toString());
assert.equal(text.toString(), "Hello 👋 from Python");

console.log("Round trip passed.");