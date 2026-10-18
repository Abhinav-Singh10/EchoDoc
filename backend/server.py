import asyncio

import grpc

from backend.service import SystemService
from collab.system.v1 import system_pb2_grpc


async def serve():
    
    server = grpc.aio.server()
    service = SystemService()

    
    system_pb2_grpc.add_SystemServiceServicer_to_server(
        service, server
    )


    server.add_insecure_port(address)


    print(f"Server listening on {address}", flush=True) # flush=True immediately flushes Python's output buffer.
    print(f"Process instance: {service.process_instance_id}", flush=True)


    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=3) 
        
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass