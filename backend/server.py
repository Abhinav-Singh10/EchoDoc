import asyncio
from contextlib import closing
from pathlib import Path
import json

import grpc
import os
import logging


from backend.service import SystemService
from collab.system.v1 import system_pb2_grpc

from backend.document_service import DocumentService
from backend.document_store import DocumentStore
from backend.raft_store import RaftStore
from backend.raft_node import RaftNode, validate_members
from backend.state_machine import StateMachine
from collab.raft.v1 import raft_pb2_grpc
from collab.document.v1 import document_pb2_grpc
from backend.writing_service import WritingService
from collab.ai.v1 import ai_pb2_grpc

from backend.auth_service import AuthService
from collab.auth.v1 import auth_pb2_grpc


async def serve():

    server = grpc.aio.server()
    node_id = os.getenv("SERVER_ID", "app-1")
    address = os.getenv("APP_BIND", "127.0.0.1:50051")
    members = json.loads(os.environ["RAFT_MEMBERS"]) if "RAFT_MEMBERS" in os.environ else {node_id: address}
    validate_members(node_id, members)
    database = Path(os.getenv("DATABASE_PATH", "data/documents.sqlite3")).resolve()
    with closing(DocumentStore(database)) as store:
        store.initialize_application(members)
        await serve_application(server, node_id, address, members, database, store)


async def serve_application(server, node_id, address, members, database, store):
    with closing(RaftStore(database)) as raft_store:
        machine = StateMachine(store)
        raft_node = RaftNode(node_id, members, raft_store, state_machine=machine)
        auth_service = AuthService(store, raft_node)
        service = SystemService(raft_node)
        ai_channel = grpc.aio.insecure_channel(os.getenv("AI_ADDRESS", "127.0.0.1:50052"))
        termination = None
        try:
            document_service = DocumentService(auth_service, store, raft_node, machine)
            ai_pb2_grpc.add_WritingServiceServicer_to_server(
                WritingService(auth_service, store, ai_channel), server
            )
            document_pb2_grpc.add_DocumentServiceServicer_to_server(document_service, server)
            system_pb2_grpc.add_SystemServiceServicer_to_server(service, server)
            auth_pb2_grpc.add_AuthServiceServicer_to_server(auth_service, server)
            raft_pb2_grpc.add_RaftServiceServicer_to_server(raft_node, server)

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
            raft_task = raft_node.start()
            termination = asyncio.create_task(server.wait_for_termination())
            done, _ = await asyncio.wait((termination, raft_task), return_when=asyncio.FIRST_COMPLETED)
            if raft_task in done:
                await raft_task  # Propagate failures instead of leaving the app running.
                raise RuntimeError("Raft task stopped unexpectedly")
            await termination
        finally:
            await server.stop(grace=3)
            await raft_node.stop()
            if termination is not None:
                termination.cancel()
                await asyncio.gather(termination, return_exceptions=True)
            await ai_channel.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
