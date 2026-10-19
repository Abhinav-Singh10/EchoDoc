import asyncio
from getpass import getpass

import grpc

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