import asyncio

import grpc

from google.protobuf.empty_pb2 import Empty

from collab.system.v1 import system_pb2_grpc


async def main():
    
    
    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        
        stub = system_pb2_grpc.SystemServiceStub(channel)

        try:

            response = await stub.GetServerInfo(
                Empty(), 
                timeout=3, 
            )
        
        except grpc.aio.AioRpcError as error:
            print(f"RPC failed: {error.code().name}: {error.details()}") 
            return 
        print(response) 


if __name__ == "__main__":
    asyncio.run(main())