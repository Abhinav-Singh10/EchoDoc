"""Password verification and reads of replicated, persistent sessions."""

import asyncio
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

import grpc
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty

from backend.commands import CreateSessionCommand, RevokeSessionCommand
from backend.mutations import route_write, submit_write
from collab.auth.v1 import auth_pb2, auth_pb2_grpc

SESSION_SECONDS = int(os.getenv("SESSION_SECONDS", "1800"))


class AuthService(auth_pb2_grpc.AuthServiceServicer):
    def __init__(self, store, raft, users_file=None):
        users_file = Path(users_file or os.getenv("USERS_PATH", str(Path(__file__).with_name("users.json"))))
        self.users = json.loads(users_file.read_text(encoding="utf-8"))
        self.hasher = PasswordHasher()
        self.store = store
        self.raft = raft

    async def Login(self, request, context):
        forwarded, deadline = await route_write(self.raft, request, context, auth_pb2_grpc.AuthServiceStub, "Login")
        if forwarded is not None:
            return forwarded
        account = self.users.get(request.username)
        if account is None:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Incorrect username or password")
        try:
            await asyncio.to_thread(self.hasher.verify, account["password_hash"], request.password)
        except VerifyMismatchError:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Incorrect username or password")
        command = CreateSessionCommand(
            secrets.token_urlsafe(32), account["user_id"], account["username"],
            int(time.time()) + SESSION_SECONDS,
        )
        await submit_write(self.raft, self.store, command, context, deadline)
        return auth_pb2.LoginResponse(
            session_token=command.token,
            user=auth_pb2.User(user_id=command.user_id, username=command.username),
            expires_at=Timestamp(seconds=command.expires_at),
        )

    async def require_session(self, context):
        authorization = dict(context.invocation_metadata()).get("authorization", "")
        if not authorization.startswith("Bearer "):
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Session token required")
        token = authorization.removeprefix("Bearer ")
        try:
            session = self.store.get_session(token)
        except sqlite3.Error as error:
            self.raft._fail(error)
            await context.abort(grpc.StatusCode.INTERNAL, "Could not read the session")
        if session is None:
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid session")
        if time.time() >= session["expires_at"]:
            # Expiration is a read-time check, never a local SQL deletion.
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Session expired")
        return token, {
            "user": auth_pb2.User(user_id=session["user_id"], username=session["username"]),
            "expires_at": session["expires_at"],
        }

    async def GetCurrentUser(self, request, context):
        _, session = await self.require_session(context)
        return session["user"]

    async def Logout(self, request, context):
        forwarded, deadline = await route_write(self.raft, request, context, auth_pb2_grpc.AuthServiceStub, "Logout")
        if forwarded is not None:
            return forwarded
        token, _ = await self.require_session(context)
        await submit_write(self.raft, self.store, RevokeSessionCommand(token), context, deadline)
        return Empty()

    async def WatchSession(self, request, context):
        while True:
            _, session = await self.require_session(context)
            yield session["user"]
            await asyncio.sleep(1)
