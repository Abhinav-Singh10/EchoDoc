import asyncio

import grpc
from google.protobuf.empty_pb2 import Empty

from collab.system.v1 import system_pb2_grpc


async def main():
    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = system_pb2_grpc.SystemServiceStub(channel)
        call = stub.WatchEvents(Empty())

        try:
            # waits for the next item in call/response, non blocking
            async for event in call:
                print(
                    f"sequence={event.sequence} "
                    f"instance={event.process_instance_id} "
                    f"time={event.server_timestamp.ToJsonString()}",
                    flush=True,
                )

        except grpc.aio.AioRpcError as error:
            print(f"Stream failed: {error.code().name}: {error.details()}")
        finally:
            call.cancel()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass