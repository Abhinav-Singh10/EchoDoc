import asyncio

import grpc

import logging


from backend.service import SystemService
from collab.system.v1 import system_pb2_grpc


async def serve():

    server = grpc.aio.server()
    service = SystemService()

    system_pb2_grpc.add_SystemServiceServicer_to_server(service, server)

    server.add_insecure_port(address)

    print(f"Server listening on {address}", flush=True)

    print(f"Process instance: {service.process_instance_id}", flush=True)

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=3)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:

        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
