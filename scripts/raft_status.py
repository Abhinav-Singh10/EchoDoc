import asyncio

import grpc
from google.protobuf.empty_pb2 import Empty

from collab.system.v1 import system_pb2_grpc


async def inspect_node(node):
    address = node["address"]
    async with grpc.aio.insecure_channel(address) as channel:
        try:
            info = await system_pb2_grpc.SystemServiceStub(channel).GetServerInfo(Empty(), timeout=1)
            return (node["id"], address, info.raft_role, str(info.raft_term),
                    info.raft_leader_id or "unknown", str(info.raft_last_log_index),
                    str(info.raft_commit_index), str(info.raft_last_applied))
        except grpc.RpcError:
            return (node["id"], address, "unreachable", "-", "-", "-", "-", "-")


async def show_status(config):
    rows = [("NODE", "ADDRESS", "ROLE", "TERM", "KNOWN LEADER", "LOG", "COMMIT", "APPLIED")]
    rows.extend(await asyncio.gather(*(inspect_node(node) for node in config["nodes"])))
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    for row in rows:
        print("  ".join(value.ljust(width) for value, width in zip(row, widths)))


def main():
    asyncio.run(show_status({"nodes": [
        {"id": name, "address": f"{name}:50051"} for name in ("app-1", "app-2", "app-3")
    ]}))


if __name__ == "__main__":
    main()
