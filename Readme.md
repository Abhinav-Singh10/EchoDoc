# EchoDoc

EchoDoc is a shared notes editor built for the Advanced Operating Systems course
project. Open the same note in two tabs, edit from either one and see the
changes appear in both. It also has a writing assistant that runs Qwen locally
for grammar corrections, rewriting, summaries and continuations.

## Running the project

It needs Docker running on your computer. On [Mac](https://docs.docker.com/desktop/setup/install/mac-install/)
and [Windows](https://docs.docker.com/desktop/setup/install/windows-install/),
use Docker Desktop . On Windows specifically , use Linux containers
and finish the WSL2 setup if Docker asks for it. On Linux, Docker Engine with the
Compose plugin is enough.

Extract the ZIP and open Terminal or PowerShell in the extracted folder—the one
with `compose.json` and `Dockerfile`. Run:

```bash
docker compose -f compose.json up --build
```

The first run takes longer because Docker builds the app and downloads the model.
You'll need an internet connection for this. Leave the terminal open, wait for
**AI ready**, then go to **http://localhost:5273** in your browser.

You don't need to install Python, Node, Envoy or Git separately.

## Demo accounts

These two accounts are created on the first run and are provided for demo:

| Username | Password |
| --- | --- |
| alice | demo1234 |
| bob | demo1234 |

Use Alice in one tab and Bob in another to try the collaboration features.

## Interface Navigation

Once logged in, the **Account** box at the top right shows username.
**Check session** checks whether your login is still valid, and **Log out** takes you back
to the login form.

The **Documents** panel on the left is where you create and open notes. Enter a
title, click **Create document**, then click the note's name. Use **Refresh
documents** to update the list, especially when a note was created in another tab.
It also refreshes the revision numbers shown in the sidebar.

The large box in the middle is the **editor**. Just start typing; there is no Save
button. Above it, beside the document title, see the current revision,
save status and connected participants. The revision increases as updates are
saved. Wait for **Saved** before closing the tab. **Close preview** closes the
open editor but keeps the note in your document list.

**Open connections** counts tabs viewing that note, including your own. Two tabs
logged in as Alice still count as two connections. The names beside the count
show who is **editing** and who is **viewing**. After someone stops typing, their
status returns to viewing after a short pause.

The **Writing assistant** sits to the right of the editor, or below it on smaller
screens. Its suggestions appear as previews. You choose whether to apply them.

## A quick walkthrough

### Editing together

1. Log in as Alice, create a note : say `OS Notes` and open it.
2. Open a second browser tab and log in as Bob. Click **Refresh documents** and
   open the same note.
3. Write a sentence in Alice's tab, then add another in Bob's. Both should show
   the same text and saved revision. You should also see two connections and the
   participant status change as each person types.
4. Wait for **Saved**, then reload one tab. Log in again, refresh the list and
   reopen the note. Your text should still be there.

### Using the writing assistant

Try typing this sentence, then wait for **Saved**:

- **Fix grammar:** `Select the sentence` and click the button. Read the preview,
  then choose **Apply to document**. The corrected text should appear in Bob's
  tab as well.
- **Enhance:** `Select some text` to get a clearer rewrite. Applying the result
  replaces the selected passage.
- **Continue:** `Leave nothing selected` and place the cursor after some text.
  The assistant suggests what could come next. Apply inserts it at that position.
- **Summarize:** `Select a passage to summarize`, or `leave nothing selected` to use
  the whole note. A summary is for reading only, so it has no Apply button.

To try **Suggest after typing pauses**, tick the checkbox, type at the end of the
note and pause. Once the edit is saved and a short delay has passed, a continuation
preview should appear. It won't be inserted on its own.

Use **Dismiss** to discard a preview. While a request is running, **Cancel** stops
the app from waiting for it, though the model may still need time to finish the
work already in progress. The model runs on your computer's CPU, so response time
will depend on the machine. Read its output before applying it.

Keep your selection in place while reviewing a suggestion. You can test what
happens when a suggestion becomes outdated: request **Enhance** in Alice's tab,
then edit the note in Bob's. Alice's preview should report that the document or
selection changed, and Apply should be disabled. Request a new suggestion to
continue.

### Checking that notes survive a restart

Wait for **Saved**, then press **Ctrl+C** in the terminal running Docker Compose.
Start the app again with the same command:

```bash
docker compose -f compose.json up --build
```

Log in and reopen your note. The saved text should still be there, and the model
should use its existing download.

If you kept the editor open while the server was stopped, use **Check session**
and log in again when prompted. Use **Reconnect** if it appears, then **Retry save**
if there are unconfirmed edits. Keep that tab open until it says Saved; reloading
would lose any edits that haven't reached the server.

## When you're finished

Press **Ctrl+C** to stop the app. To remove the stopped containers as well, run:

```bash
docker compose -f compose.json down
```

Your saved notes, demo accounts and downloaded model stay in Docker volumes.
Don't add `-v` unless you want to delete them too.
