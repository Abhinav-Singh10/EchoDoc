import asyncio
import uuid
from getpass import getpass

import grpc
from pycrdt import Doc, Text

from collab.auth.v1 import auth_pb2, auth_pb2_grpc
from collab.document.v1 import document_pb2, document_pb2_grpc


async def main():
    username = input("Username: ")
    password = getpass("Password: ")
    document_id = input("Document ID: ").strip()

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        auth = auth_pb2_grpc.AuthServiceStub(channel)
        documents = document_pb2_grpc.DocumentServiceStub(channel)

        login = await auth.Login(
            auth_pb2.LoginRequest(
                username=username,
                password=password,
            ),
            timeout=5,
        )

        metadata = (
            ("authorization", f"Bearer {login.session_token}"),
        )

        doc = Doc()
        text = doc.get("content", type=Text)

        call = documents.WatchDocument(
            document_pb2.WatchDocumentRequest(
                document_id=document_id,
                connection_id=str(uuid.uuid4()),
            ),
            metadata=metadata,
        )

        print("Watching document. Press Ctrl+C to stop.", flush=True)

        try:
            async for event in call:
                doc.apply_update(event.update)

                print(
                    f"{event.kind}: revision={event.revision}",
                    flush=True,
                )
                print("Text:", repr(str(text)), flush=True)
        finally:
            call.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except grpc.aio.AioRpcError as error:
        print(f"RPC failed: {error.code().name}: {error.details()}")
    except KeyboardInterrupt:
        print("Watch stopped.")