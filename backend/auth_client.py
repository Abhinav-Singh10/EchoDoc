import asyncio
import grpc
import uuid

from pycrdt import Doc, Text
from getpass import getpass
from collab.document.v1 import document_pb2, document_pb2_grpc
from collab.auth.v1 import auth_pb2, auth_pb2_grpc
from google.protobuf.empty_pb2 import Empty

async def main():
    username = input("Username: ")
    password = getpass("Password: ")

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = auth_pb2_grpc.AuthServiceStub(channel)

        try:
            response = await stub.Login(
                auth_pb2.LoginRequest(
                    username=username,
                    password=password,
                ),
                timeout=5,
            )
        except grpc.aio.AioRpcError as error:
            print(f"{error.code().name}: {error.details()}")
            return

        print(f"Logged in as: {response.user.username}")
        print(f"User ID: {response.user.user_id}")
        print(f"Expires at: {response.expires_at.ToJsonString()}")
        print("Session token received:", bool(response.session_token))

        metadata = (
            ("authorization", f"Bearer {response.session_token}"),
        )

        documents = document_pb2_grpc.DocumentServiceStub(channel)

        result = await documents.ListDocuments(
            Empty(),
            metadata=metadata,
            timeout=5,
        )

        print("Saved documents:", len(result.documents))


        for document in result.documents:
            print(
                document.document_id,
                document.title,
                f"revision={document.revision}",
            )

        if result.documents:
            selected = result.documents[0]

            loaded = await documents.GetDocument(
                    document_pb2.GetDocumentRequest(
                    document_id=selected.document_id,
                    ),
                    metadata=metadata,
                    timeout=5,
            )

            local_doc = Doc()
            local_doc.apply_update(loaded.state)
            text = local_doc.get("content", type=Text)

            print("Opened:", loaded.document.title)
            print("Text:", repr(str(text)))
            print("Revision:", loaded.document.revision)

            addition = input("Text to append (Enter to only read): ")

            if addition:
                before = local_doc.get_state()
                text += addition
                update = local_doc.get_update(before)

                try:
                    saved = await documents.SubmitUpdate(
                        document_pb2.SubmitUpdateRequest(
                            document_id=selected.document_id,
                            request_id=str(uuid.uuid4()),
                            update=update,
                        ),
                        metadata=metadata,
                        timeout=5,
                    )
                except grpc.aio.AioRpcError as error:
                    print(
                        "Save not confirmed:",
                        error.code().name,
                        error.details(),
                    )
                else:
                    print("Saved revision:", saved.revision)

        user = await stub.GetCurrentUser(
            Empty(),
            metadata=metadata,
            timeout=5,
        )
        print(f"Protected call succeeded: {user.username}")

        try:
            await stub.GetCurrentUser(Empty(), timeout=5)
        except grpc.aio.AioRpcError as error:
            print(f"Without token: {error.code().name}: {error.details()}")
        else:
            print("BUG: request without a token was accepted")

        await stub.Logout(
            Empty(),
            metadata=metadata,
            timeout=5,
        )
        print("Logged out")

        try:
            await stub.GetCurrentUser(
                Empty(),
                metadata=metadata,
                timeout=5,
            )
        except grpc.aio.AioRpcError as error:
            print(f"After logout: {error.code().name}: {error.details()}")
        else:
            print("BUG: logged-out token was accepted")

if __name__ == "__main__":
    asyncio.run(main())