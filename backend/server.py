import asyncio
from contextlib import closing
from pathlib import Path

import grpc
import os
import logging


from backend.service import SystemService
from collab.system.v1 import system_pb2_grpc

from backend.document_service import DocumentService
from backend.document_store import DocumentStore
from backend.raft_store import RaftStore
from collab.document.v1 import document_pb2_grpc
from backend.writing_service import WritingService
from collab.ai.v1 import ai_pb2_grpc

from backend.auth_service import AuthService
from collab.auth.v1 import auth_pb2_grpc


async def serve():

    server = grpc.aio.server()
    service = SystemService()
    auth_service = AuthService()
    database = Path(os.getenv("DATABASE_PATH", "data/documents.sqlite3")).resolve()
    with closing(DocumentStore(database)) as store, closing(RaftStore(database)) as raft_store:
        ai_channel = grpc.aio.insecure_channel(os.getenv("AI_ADDRESS", "127.0.0.1:50052"))
        try:
            document_service = DocumentService(auth_service, store)
            ai_pb2_grpc.add_WritingServiceServicer_to_server(
                WritingService(auth_service, store, ai_channel), server
            )
            document_pb2_grpc.add_DocumentServiceServicer_to_server(document_service, server)
            system_pb2_grpc.add_SystemServiceServicer_to_server(service, server)
            auth_pb2_grpc.add_AuthServiceServicer_to_server(auth_service, server)

            address = os.getenv("APP_BIND", "127.0.0.1:50051")
            if not server.add_insecure_port(address):
                raise RuntimeError(f"Could not bind {address}")
            await server.start()

            print(f"Node: {service.server_id}", flush=True)
            print(f"Server listening on {address}", flush=True)
            print(f"Process instance: {service.process_instance_id}", flush=True)
            state = raft_store.get_state()
            last_index, last_term = raft_store.last_log_position()
            print(
                f"Raft state: term={state['current_term']}, voted_for={state['voted_for']}, "
                f"last_log=({last_index}, {last_term})", flush=True,
            )
            await server.wait_for_termination()
        finally:
            await server.stop(grace=3)
            await ai_channel.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
