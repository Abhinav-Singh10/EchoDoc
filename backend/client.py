import asyncio

import grpc
# The generated standard message type for our Empty request
from google.protobuf.empty_pb2 import Empty

from collab.system.v1 import system_pb2_grpc


async def main():
    
    # async with ... as channel-> Manage the channel's lifetime and close it when leaving the block, including on errors

    # grpc.aio.insecure...-> Create a client communication channel targeting the server,Creating it alone doesn't prove connectivity 

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        # create the generated client interface for our RPC methods
        stub = system_pb2_grpc.SystemServiceStub(channel)

        try:
            # Make a remote call and wait asynchronously for its response
            response = await stub.GetServerInfo(
                Empty(), # Construct the request message; the call still sends a request even though it has no application fields
                timeout=3, # Give this RPC a three seconds time limit, in secs
            )
        # Handle an RPC failure, such as an unavailable server or exceeded deadline
        except grpc.aio.AioRpcError as error:
            print(f"RPC failed: {error.code().name}: {error.details()}") # Get the readable gRPC status name and the accompanying error descrp.
            return # leave main after reporting the failure

        print(response) # Display the returned protobuf message in readable text form


if __name__ == "__main__":
    asyncio.run(main())