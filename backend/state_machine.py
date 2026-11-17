"""Apply ordered log entries and publish document changes after persistence."""

import asyncio
from collections import defaultdict

from backend.commands import CreateDocumentCommand, SubmitUpdateCommand
from backend.raft_commands import decode_command


class StateMachine:
    def __init__(self, store):
        self.store = store
        self.locks = defaultdict(asyncio.Lock)
        self.on_update = None

    async def apply(self, entry):
        command = decode_command(entry.command)
        if isinstance(command, (CreateDocumentCommand, SubmitUpdateCommand)):
            async with self.locks[command.document_id]:
                outcome = self.store.apply_committed(entry.index, command)
                if (isinstance(command, SubmitUpdateCommand) and outcome.changed
                        and not outcome.error_code and self.on_update is not None):
                    self.on_update(command, outcome)
                return outcome
        return self.store.apply_committed(entry.index, command)
