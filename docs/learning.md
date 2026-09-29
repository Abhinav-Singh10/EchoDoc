# Read the project in small steps

Use `git log --reverse --oneline 0e29e3a..HEAD` and `git show <commit>` to read one
change at a time. The sequence deliberately keeps each new concept small.

## 1. Messages and remote calls

Start with `proto/collab/`: a service declares callable methods; each message is
the agreed shape of a request or response. Generation creates matching Python
and TypeScript definitions, so neither side needs to hand-parse network data.
Read the [Protocol Buffers guide](https://protobuf.dev/programming-guides/proto3/)
and [gRPC Python basics](https://grpc.io/docs/languages/python/basics/).

`frontend/src/rpc.ts` sends gRPC-Web through Vite's `/rpc` proxy and Envoy to Python.
A unary RPC returns once; `WatchDocument` stays open and yields many events.
[Connect cancellation and timeouts](https://connectrpc.com/docs/web/cancellation-and-timeouts/)
explains why we pass an AbortSignal and why save requests have deadlines.

## 2. Concurrent editing and retries

Read `DocumentPreview.tsx` beside `backend/document_service.py`.
Yjs represents edits as binary CRDT updates. Updates can merge in different
orders and can be applied repeatedly without duplicating the text.
See [Yjs document updates](https://docs.yjs.dev/api/document-updates).

That property alone does not deduplicate our database revision counter. The
backend also records each request ID and its original response revision. A retry
must reuse the same ID and update bytes. Remote-origin updates are not sent back
as new local edits, preventing an echo loop.

Per-document locks protect snapshot/subscription and update ordering. Each
subscriber has its own queue: broadcasting adds an event to every queue;
a stream awaits its queue. Read [asyncio queues](https://docs.python.org/3/library/asyncio-queue.html)
and [asyncio locks](https://docs.python.org/3/library/asyncio-sync.html#lock).

## 3. React lifetime and recovery

An editor effect owns a stream, timer and CodeMirror instance. Its cleanup
cancels and removes them. The Yjs document and pending queue survive a same-user
re-login in component state. A page reload destroys that in-memory state.
[React useEffect](https://react.dev/reference/react/useEffect) explains this lifecycle.
Use `onPendingChange` to follow how unconfirmed edits block navigation/logout.

## 4. Local AI and reviewed changes

Read `WritingPanel.tsx`, `backend/writing_service.py`, then `ai/service.py`.
A request captures selection, local edit version and server revision. Apply
checks them again, so an old answer cannot overwrite newer edits. A summary is
never inserted. One worker thread serializes access to the model while the async
server continues handling RPCs. The queue accepts only a small amount of work.

The [official Qwen model card](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF)
explains the GGUF model variants. `ai/model.py` loads the quantized model on CPU,
uses action-specific prompts, and bounds input/output size. Model quality is
separate from transport correctness: a successful RPC can still contain a poor
suggestion, which is why this app uses preview and explicit Apply.
