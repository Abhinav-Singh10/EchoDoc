import argparse
import asyncio

import grpc
from google.protobuf.empty_pb2 import Empty

from collab.system.v1 import system_pb2_grpc
from scripts.run_local import load_config


async def inspect_node(node):
    address = f"127.0.0.1:{node['app_port']}"
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
    parser = argparse.ArgumentParser(description="Show each configured node's own view of the election, over native gRPC.")
    parser.add_argument("--config", default="deploy/local.json")
    args = parser.parse_args()
    asyncio.run(show_status(load_config(args.config)))


if __name__ == "__main__":
    main()
