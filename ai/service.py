"""Keep blocking CPU inference off the gRPC event loop."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import grpc
from collab.ai.v1 import ai_pb2 as pb, ai_pb2_grpc
from ai.model import MODEL_FILE, generate
from ai.validation import validate


class AIService(ai_pb2_grpc.AIServiceServicer):
    def __init__(self, model):
        self.model = model
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.jobs = set()

    async def GetStatus(self, request, context):
        return pb.AIStatus(ready=True, model=MODEL_FILE)

    async def GetLLMAnswer(self, request, context):
        await validate(request, context)
        if len(self.jobs) >= 3:
            await context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, 'Model is busy; try again shortly')
        future = self.executor.submit(generate, self.model, request)
        self.jobs.add(future)
        loop = asyncio.get_running_loop()
        future.add_done_callback(lambda job: loop.call_soon_threadsafe(self.jobs.discard, job))
        try:
            answer = await asyncio.wrap_future(future)
        except ValueError as error:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(error))
        except asyncio.CancelledError:
            future.cancel()  # Cancels queued work; running inference retains its slot.
            raise
        except Exception:
            await context.abort(grpc.StatusCode.INTERNAL, 'Local model generation failed')
        return pb.AnswerResponse(request_id=request.request_id, answer=answer,
                                 source_revision=request.source_revision)
