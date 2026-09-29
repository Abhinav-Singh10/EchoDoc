"""Authenticated forwarding from the application to the internal AI service."""
import grpc
from collab.ai.v1 import ai_pb2_grpc
from ai.validation import validate


class WritingService(ai_pb2_grpc.WritingServiceServicer):
    def __init__(self, auth, documents, channel):
        self.auth = auth
        self.documents = documents
        self.client = ai_pb2_grpc.AIServiceStub(channel)

    async def GetLLMAnswer(self, request, context):
        await self.auth.require_session(context)
        await validate(request, context)
        row = self.documents.db.execute('SELECT revision FROM documents WHERE id = ?',
                                        (request.document_id,)).fetchone()
        if row is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, 'Document not found')
        if row['revision'] != request.source_revision:
            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, 'Document changed; request a fresh result')
        try:
            remaining = context.time_remaining()
            response = await self.client.GetLLMAnswer(request, timeout=min(45, remaining) if remaining else 45)
        except grpc.aio.AioRpcError as error:
            await context.abort(error.code(), 'AI service: ' + error.details())
        await self.auth.require_session(context)
        return response
