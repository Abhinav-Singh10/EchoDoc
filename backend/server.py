#asyncio provides Python's event loop , which schedules async work. we'll later use it to handle multiple streams while they wait b/w events 
import asyncio

import grpc

from backend.service import SystemService
from collab.system.v1 import system_pb2_grpc


async def serve():
    # These create 2 diff objects. 1) server -> manages RPC conncections and dispatches incoming calls.
    # 2) service -> contains our app logic and the state initialized in __int__
    # We create the service once here, so req share its PID (process id) and startup time

    server = grpc.aio.server()
    service = SystemService()

    # This generated function registers your impl. with the server. It connects the incoming RPC method names to your python methods and configures message serialization
    system_pb2_grpc.add_SystemServiceServicer_to_server(
        service, server
    )

    #127.0.0.1 is the loopback address: clients on this Mac can connect
    # 50051 is the TCP port identifying our listening service
    # insecure means this connection uses no TLS encryption

    # A 2nd lappy can't reach a server bound only to 1287.0.0.1. That fits our current local setup
    address = "127.0.0.1:50051"
    server.add_insecure_port(address)

# Start accepting RPC's. await lets this corountine wait for the operation while allowing the event loop to run other ready work.
    await server.start()
    print(f"Server listening on {address}", flush=True) # flush=True immediately flushes Python's output buffer.
    print(f"Process instance: {service.process_instance_id}", flush=True)


    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=3) # finally block performs shutdown, allowing existing RPCs up to three seconds to finish before aborting them


# run this block when the module is executed directly, rather than when another module imports it
if __name__ == "__main__":
    try:
        # creates and manages the event loop
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass