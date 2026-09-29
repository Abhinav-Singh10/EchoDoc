#asyncio provides Python's event loop , which schedules async work. we'll later use it to handle multiple streams while they wait b/w events 
import asyncio
import logging
import os
import grpc

from backend.service import SystemService
from collab.system.v1 import system_pb2_grpc
from backend.document_service import DocumentService
from collab.document.v1 import document_pb2_grpc
from backend.writing_service import WritingService
from collab.ai.v1 import ai_pb2_grpc
from backend.auth_service import AuthService
from collab.auth.v1 import auth_pb2_grpc


async def serve():
    # These create 2 diff objects. 1) server -> manages RPC conncections and dispatches incoming calls.
    # 2) service -> contains our app logic and the state initialized in __int__
    # We create the service once here, so req share its app generated process instance id (process id) and startup time

    server = grpc.aio.server()
    service = SystemService()
    auth_service = AuthService()
    document_service = DocumentService(auth_service)
    ai_channel = grpc.aio.insecure_channel(os.getenv("AI_ADDRESS", "127.0.0.1:50052"))
    ai_pb2_grpc.add_WritingServiceServicer_to_server(
        WritingService(auth_service, document_service, ai_channel), server)

    document_pb2_grpc.add_DocumentServiceServicer_to_server(
        document_service, server
    )

    # This generated function registers your impl. with the server. It connects the incoming RPC method names to your python methods and configures message serialization
    system_pb2_grpc.add_SystemServiceServicer_to_server(
        service, server
    )

    
    auth_pb2_grpc.add_AuthServiceServicer_to_server(
        auth_service, server
    )

    #127.0.0.1 is the loopback address: clients on this Mac can connect
    # 50051 is the TCP port identifying our listening service
    # insecure means this connection uses no TLS encryption

    # A 2nd lappy can't reach a server bound only to 1287.0.0.1. That fits our current local setup
    address = os.getenv("APP_BIND", "127.0.0.1:50051")
    if not server.add_insecure_port(address):
        raise RuntimeError(f"Could not bind {address}")

# Start accepting RPC's. await lets this corountine wait for the operation while allowing the event loop to run other ready work.
    await server.start()
    print(f"Server listening on {address}", flush=True) # flush=True immediately flushes Python's output buffer. Needed for when we'll deploy it as aws is block buffering and not line bufferiing, due to which when deployed we may only see till Server listening on ....
    print(f"Process instance: {service.process_instance_id}", flush=True)


    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=3) # finally block performs shutdown, allowing existing RPCs up to three seconds to finish before aborting them

        document_service.db.close()
        await ai_channel.close()

# run this block when the module is executed directly, rather than when another module imports it
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        # asctime -> Human Readable time
        # levelname -> Severity of the entry (one of these enums-> debug, info, warning, error or critical) Due to us setting logging.INFO logger.debug won't show
        # name -> Loggers name (here it will be backend.service as logging module for imported there as __name__ is this)
        # message -> complete message
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    
    try:
        # creates and manages the event loop
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
