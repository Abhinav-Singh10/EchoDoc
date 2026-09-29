"""Shared request checks for the application and model services."""
import grpc
from collab.ai.v1 import ai_pb2 as pb


async def validate(request, context):
    if request.action not in (pb.GRAMMAR, pb.SUGGEST, pb.SUMMARIZE, pb.ENHANCE):
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'Choose a supported writing action')
    if not request.request_id or not request.text.strip():
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, 'Request ID and text are required')
    if len(request.text) > 4000 or len(request.context) > 2000:
        await context.abort(grpc.StatusCode.INVALID_ARGUMENT,
                            'Limit: 4,000 text characters and 2,000 context characters. Shorten the input.')
