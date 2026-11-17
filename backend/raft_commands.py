"""Convert prepared commands to and from Raft log payloads, without applying them."""

from dataclasses import dataclass

from google.protobuf.message import DecodeError

from backend.document_store import CreateDocumentCommand, SubmitUpdateCommand
from collab.raft.v1 import raft_pb2


@dataclass(frozen=True)
class NoOpCommand:
    pass


def encode_command(command):
    if isinstance(command, CreateDocumentCommand):
        envelope = raft_pb2.Command(create_document=raft_pb2.CreateDocumentCommand(
            document_id=command.document_id, title=command.title, state=command.state,
        ))
    elif isinstance(command, SubmitUpdateCommand):
        envelope = raft_pb2.Command(submit_update=raft_pb2.SubmitUpdateCommand(
            document_id=command.document_id, request_id=command.request_id,
            author=command.author, update=command.update,
        ))
    elif isinstance(command, NoOpCommand):
        envelope = raft_pb2.Command(no_op=raft_pb2.NoOpCommand())
    else:
        raise TypeError(f"Unsupported document command: {type(command).__name__}")
    return envelope.SerializeToString(deterministic=True)


def decode_command(payload):
    try:
        envelope = raft_pb2.Command.FromString(payload)
    except DecodeError as error:
        raise ValueError("Malformed Raft command") from error
    kind = envelope.WhichOneof("command")
    if kind == "create_document":
        command = envelope.create_document
        return CreateDocumentCommand(command.document_id, command.title, command.state)
    elif kind == "submit_update":
        command = envelope.submit_update
        return SubmitUpdateCommand(
            command.document_id, command.request_id, command.author, command.update,
        )
    elif kind == "no_op":
        return NoOpCommand()
    raise ValueError("Raft command has no supported command variant")
