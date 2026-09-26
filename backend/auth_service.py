import asyncio
import json
import secrets
import time
from pathlib import Path

import grpc
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty

from collab.auth.v1 import auth_pb2, auth_pb2_grpc

# Auth token validity limit
SESSION_SECONDS = 30 * 60


class AuthService(auth_pb2_grpc.AuthServiceServicer):
    def __init__(self):
        users_file = Path(__file__).with_name("users.json")
        self.users = json.loads(users_file.read_text(encoding="utf-8"))
        self.hasher = PasswordHasher()
        self.sessions = {} # session are stored in a python dict for now-> later we'll store it in a db

    async def Login(self, request, context):

        account = self.users.get(request.username)

        if account is None:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Incorrect username or password",
            )

        try:
            # use to_thread to let the eventloop continue to handle other rpcs (WatchEvents) while verification runs, awaiting it pauses it till it finihes verifying
            await asyncio.to_thread(
                self.hasher.verify,
                account["password_hash"],
                request.password,
            )
        except VerifyMismatchError:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Incorrect username or password",
            )

        user = auth_pb2.User(
            user_id=account["user_id"],
            username=account["username"],
        )

        token = secrets.token_urlsafe(32)
        expires_at = int(time.time()) + SESSION_SECONDS

        self.sessions[token] = {
            "user": user,
            "expires_at": expires_at,
        }

        return auth_pb2.LoginResponse(
            session_token=token,
            user=user,
            expires_at=Timestamp(seconds=expires_at),
        )


    async def require_session(self, context):
        metadata = dict(context.invocation_metadata())
        authorization = metadata.get("authorization", "")

        if not authorization.startswith("Bearer "):
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Session token required",
            )

        token = authorization.removeprefix("Bearer ")
        session = self.sessions.get(token)

        if session is None:
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Invalid session",
            )

        if time.time() >= session["expires_at"]:
            del self.sessions[token]
            await context.abort(
                grpc.StatusCode.UNAUTHENTICATED,
                "Session expired",
            )

        return token, session

    async def GetCurrentUser(self, request, context):
        _, session = await self.require_session(context)
        return session["user"]

    async def Logout(self, request, context):
        token, _ = await self.require_session(context)
        del self.sessions[token]
        return Empty()