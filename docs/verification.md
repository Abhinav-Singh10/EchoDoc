# Demo verification — 2026-09-29

Verified locally on macOS with `deploy/demo.json` and the real CPU Qwen model.

## Browser checks

- Alice created a note; Bob opened it in a second tab.
- Both tabs received identical saved content and revision values.
- Presence showed both users and changed between editing and viewing.
- Grammar preview applied as a shared edit visible to Bob.
- A Bob edit made Alice's pending enhancement stale and disabled Apply.
- Summary showed a preview with no Apply control.
- Pausing the demo gateway left 16 unconfirmed edits in the editor. Switching
  documents, closing the preview and logout were disabled. Resuming the gateway
  and clicking Retry save saved all 16 without duplicating text.
- Stopping the full launcher made the editor read-only. After restart and login,
  the saved note reopened at revision 98 with its text intact.

## Reproducible checks

`PYTHONPATH=backend/generated .venv/bin/python scripts/check_demo.py` passed:
unauthenticated rejection, persistence, concurrent duplicate request handling,
all four real-model actions, stale-revision rejection, invalid-action rejection,
and rejection of a logged-out session.

Python and TypeScript regeneration completed without tracked output changes.
Frontend build and lint passed. Python compilation, both environments' `pip check`,
and Envoy configuration validation passed. The build reports a large editor
bundle; native Envoy reports its expected macOS reuse-port warning.

## Limits of this verification

The browser check used two tabs on one computer. No second-device or production
deployment claim is made. Model responses vary with input and need review.
Pending drafts and sessions are in memory; only confirmed content is durable.
