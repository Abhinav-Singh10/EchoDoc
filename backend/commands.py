from dataclasses import dataclass


@dataclass(frozen=True)
class CreateDocumentCommand:
    document_id: str
    title: str
    state: bytes


@dataclass(frozen=True)
class SubmitUpdateCommand:
    document_id: str
    request_id: str
    author: str
    update: bytes


@dataclass(frozen=True)
class NoOpCommand:
    pass


@dataclass(frozen=True)
class CreateSessionCommand:
    token: str
    user_id: str
    username: str
    expires_at: int


@dataclass(frozen=True)
class RevokeSessionCommand:
    token: str


@dataclass(frozen=True)
class CommandOutcome:
    revision: int | None = None
    changed: bool = False
    error_code: str | None = None
    error_message: str | None = None
