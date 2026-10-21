import asyncio

import grpc
import os
import logging


from backend.service import SystemService
from collab.system.v1 import system_pb2_grpc

from backend.document_service import DocumentService
from collab.document.v1 import document_pb2_grpc

from backend.auth_service import AuthService
from collab.auth.v1 import auth_pb2_grpc


async def serve():

    server = grpc.aio.server()
    service = SystemService()
    auth_service = AuthService()
    document_service = DocumentService(auth_service)

    document_pb2_grpc.add_DocumentServiceServicer_to_server(document_service, server)

    system_pb2_grpc.add_SystemServiceServicer_to_server(service, server)

    auth_pb2_grpc.add_AuthServiceServicer_to_server(auth_service, server)

    address = os.getenv("APP_BIND", "127.0.0.1:50051")
    if not server.add_insecure_port(address):
        raise RuntimeError(f"Could not bind {address}")

    await server.start()

    print(f"Server listening on {address}", flush=True)

    print(f"Process instance: {service.process_instance_id}", flush=True)

    try:
        await server.wait_for_termination()
    finally:
        await server.stop(grace=3)

    document_service.db.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
