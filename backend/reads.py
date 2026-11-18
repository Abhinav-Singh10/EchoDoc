import asyncio
import sqlite3

import grpc

from backend.raft_node import NotLeaderError
from collab.raft.v1 import raft_pb2, raft_pb2_grpc


async def consistent_read(raft, context):
    budget = context.time_remaining()
    timeout = min(2.0, budget) if budget is not None else 2.0
    try:
        async with asyncio.timeout(timeout):
            async with raft.lock:
                role, leader = raft.role, raft.leader_id
            if role == "leader":
                return await raft.read_barrier(timeout)
            if not leader or leader == raft.node_id:
                raise NotLeaderError(leader)
            async with grpc.aio.insecure_channel(raft.members[leader]) as channel:
                response = await raft_pb2_grpc.RaftServiceStub(channel).ReadBarrier(
                    raft_pb2.ReadBarrierRequest(requester_id=raft.node_id), timeout=timeout,
                )
                await raft.wait_applied(response.read_index, timeout)
                return response.read_index
    except (NotLeaderError, TimeoutError, RuntimeError):
        await context.abort(grpc.StatusCode.UNAVAILABLE, "Could not confirm a fresh read; retry when a majority is available")
    except grpc.RpcError as error:
        await context.abort(grpc.StatusCode.UNAVAILABLE, "Read barrier unavailable: " + error.details())
    except (sqlite3.Error, OverflowError) as error:
        raft._fail(error)
        await context.abort(grpc.StatusCode.INTERNAL, "Could not read Raft state")
