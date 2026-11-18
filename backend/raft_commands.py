from google.protobuf.message import DecodeError

from backend.commands import (
    CreateDocumentCommand, CreateSessionCommand, NoOpCommand, RevokeSessionCommand,
    SubmitUpdateCommand,
)
from collab.raft.v1 import raft_pb2


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
    elif isinstance(command, CreateSessionCommand):
        envelope = raft_pb2.Command(create_session=raft_pb2.CreateSessionCommand(
            token=command.token, user_id=command.user_id, username=command.username,
            expires_at=command.expires_at,
        ))
    elif isinstance(command, RevokeSessionCommand):
        envelope = raft_pb2.Command(revoke_session=raft_pb2.RevokeSessionCommand(token=command.token))
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
    elif kind == "create_session":
        command = envelope.create_session
        return CreateSessionCommand(command.token, command.user_id, command.username, command.expires_at)
    elif kind == "revoke_session":
        return RevokeSessionCommand(envelope.revoke_session.token)
    raise ValueError("Raft command has no supported command variant")
