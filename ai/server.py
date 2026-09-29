"""Run the local CPU model as a separate gRPC process."""
import asyncio
import os
import grpc
from ai.model import load
from ai.service import AIService
from collab.ai.v1 import ai_pb2_grpc


async def serve():
    print('Loading local model on CPU...', flush=True)
    model = load()
    service = AIService(model)
    server = grpc.aio.server()
    ai_pb2_grpc.add_AIServiceServicer_to_server(service, server)
    address = os.getenv('AI_BIND', '127.0.0.1:50052')
    if not server.add_insecure_port(address):
        raise RuntimeError(f'Could not bind {address}')
    await server.start()
    print(f'AI ready on {address}', flush=True)
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(3)
        service.executor.shutdown(wait=True, cancel_futures=True)
        model.close()


if __name__ == '__main__':
    try: asyncio.run(serve())
    except KeyboardInterrupt: pass
