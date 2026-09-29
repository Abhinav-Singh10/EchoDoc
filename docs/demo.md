# Five-minute demo walkthrough

Follow [setup.md](setup.md), start `deploy/demo.json`, and wait for AI ready.
Use two tabs at http://127.0.0.1:5273: Alice in one, Bob in the other.
Passwords are `demo1234` when accounts were created with `--demo`.

## 1. Shared document and persistence

1. Alice creates `Operating Systems Notes`, then clicks its name to open it.
2. Bob clicks **Refresh documents**, then opens the same note.
3. Type in each tab. Both should show identical text and the same saved revision.
4. Show the participant list switching between **editing** and **viewing**.
   Each open tab counts as a connection, even for the same username.
5. Wait for **Saved**, reload one tab, log in and reopen the note. Text remains.

Explain: Yjs merges text edits; protobuf carries binary updates. Python stores
accepted state and a numeric revision in SQLite before broadcasting the update.
The revision orders accepted requests; it is not the CRDT's own logical clock.

## 2. Local AI assistance

Paste: `The team are building a shared editor. It save changes for everyone.`

1. Wait for Saved, select the passage, then **Fix grammar**.
2. Review the preview; **Apply to document** sends it through normal collaboration.
3. With text selected, try **Enhance**. For **Continue**, collapse the selection
   and put the cursor at the end. **Summarize** uses selection or the whole note;
   its result is display-only.
4. Request Enhance in Alice, then edit in Bob. The old preview must say the
   document or selection changed and disable Apply. Request a fresh result.
5. Optionally enable **Suggest after typing pauses**. Type at the end and pause:
   one preview is requested after 1.5 seconds; nothing is inserted automatically.
6. Show **Cancel** during generation. The UI stops waiting; CPU work already in
   progress may finish before the next queued request starts.

Explain: the authenticated application checks the source revision and forwards
only writing RPCs to an internal AI worker. Qwen runs locally on CPU. Model output
can be wrong, so the user reviews it before it becomes a shared edit.

## 3. Recovery

1. Leave a saved note open. Stop the launcher with Ctrl+C, then run it again.
2. The page becomes disconnected/read-only. Restarting Vite can reload the page;
   log in, refresh the document list and reopen the note.
3. Confirm the saved text remains. Sessions live in backend memory, so a backend
   restart also requires re-login. If the page has stayed open, **Check session**
   reveals the invalid session and same-user login reconnects its mounted editor.
4. For a gateway-only interruption, restore the gateway and click **Reconnect**.
   If the UI shows unconfirmed edits, click **Retry save** after reconnecting.
   Repeated requests reuse their IDs, preventing a second revision for one save.

Keep the tab open during recovery. Pending edits are in browser memory, so do not
reload or close it until Saved. Navigation/logout are blocked while edits await
confirmation; that guard is not durable offline storage.

## Scope to state during the demo

This milestone has shared plain text, presence, authenticated RPCs, local AI and
SQLite persistence. It uses one application server, manual recovery and demo
accounts. Raft replication, rich text, registration, deployment and durable
offline drafts are outside this milestone. Do not claim a second-device test
based only on the two-tab demonstration.
