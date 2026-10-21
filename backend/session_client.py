import asyncio
from getpass import getpass

import grpc
from google.protobuf.empty_pb2 import Empty

from collab.auth.v1 import auth_pb2, auth_pb2_grpc


async def main():
    username = input("Username: ")
    password = getpass("Password: ")
    mode = input("Test logout or expiry? [logout/expiry]: ")

    async with grpc.aio.insecure_channel("127.0.0.1:50051") as channel:
        stub = auth_pb2_grpc.AuthServiceStub(channel)

        response = await stub.Login(
            auth_pb2.LoginRequest(
                username=username,
                password=password,
            ),
            timeout=5,
        )

        metadata = (
            ("authorization", f"Bearer {response.session_token}"),
        )

        stream = stub.WatchSession(
            Empty(),
            metadata=metadata,
            timeout=15,
        )

        count = 0

        try:
            async for user in stream:
                count += 1
                print(f"Event {count}: session valid for {user.username}")

                if mode == "logout" and count == 3:
                    await stub.Logout(
                        Empty(),
                        metadata=metadata,
                        timeout=5,
                    )
                    print("Logged out. Still listening to the stream...")
        except grpc.aio.AioRpcError as error:
            if error.code() != grpc.StatusCode.UNAUTHENTICATED:
                raise

            print(f"Server ended stream: {error.code().name}")
            print(error.details())
        else:
            print("Unexpected: stream ended without an authentication error")


if __name__ == "__main__":
    asyncio.run(main())