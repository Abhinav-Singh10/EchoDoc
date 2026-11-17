"""Authenticated forwarding from the application to the internal AI service."""

import grpc
from collab.ai.v1 import ai_pb2_grpc
from ai.validation import validate
from backend.document_store import DocumentStore, StoreError


class WritingService(ai_pb2_grpc.WritingServiceServicer):
    def __init__(self, auth, store: DocumentStore, channel):
        self.auth = auth
        self.store = store
        self.client = ai_pb2_grpc.AIServiceStub(channel)

    async def GetLLMAnswer(self, request, context):
        await self.auth.require_session(context)
        await validate(request, context)
        try:
            revision = self.store.get_revision(request.document_id)
        except StoreError as error:
            await context.abort(grpc.StatusCode[error.code], str(error))
        if revision != request.source_revision:
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                "Document changed; request a fresh result",
            )
        try:
            remaining = context.time_remaining()
            response = await self.client.GetLLMAnswer(
                request, timeout=min(45, remaining) if remaining else 45
            )
        except grpc.aio.AioRpcError as error:
            await context.abort(error.code(), "AI service: " + error.details())
        await self.auth.require_session(context)
        return response
