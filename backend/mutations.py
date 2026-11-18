import sqlite3
import time

import grpc

from backend.raft_commands import encode_command
from backend.raft_node import NotLeaderError

HOP = "x-raft-forwarded"
APPLIED = "x-raft-applied-index"


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError("Mutation deadline expired")
    return seconds


async def abort_mutation(context, error):
    if isinstance(error, NotLeaderError):
        await context.abort(grpc.StatusCode.UNAVAILABLE, str(error))
    if isinstance(error, TimeoutError):
        await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "Mutation outcome was not confirmed; it may still complete")
    if isinstance(error, grpc.RpcError):
        await context.abort(error.code(), error.details())
    await context.abort(grpc.StatusCode.UNAVAILABLE, "Raft application is unavailable")


async def route_write(raft, request, context, stub_type, method):
    budget = context.time_remaining()
    deadline = time.monotonic() + (min(5.0, budget) if budget is not None else 5.0)
    try:
        if raft.role != "leader":
            metadata = dict(context.invocation_metadata())
            leader = raft.leader_id
            if HOP in metadata or not leader or leader == raft.node_id:
                raise NotLeaderError(leader)
            async with grpc.aio.insecure_channel(raft.members[leader]) as channel:
                headers = [(HOP, "1")]
                if "authorization" in metadata:
                    headers.append(("authorization", metadata["authorization"]))
                call = getattr(stub_type(channel), method)(request, metadata=headers, timeout=remaining(deadline))
                response = await call
                trailers = {key: value for key, value in await call.trailing_metadata()}
                index = int(trailers[APPLIED])
                await raft.wait_applied(index, remaining(deadline))
                return response, deadline
        await raft.wait_ready(remaining(deadline))
        return None, deadline
    except (NotLeaderError, TimeoutError, RuntimeError, grpc.RpcError) as error:
        await abort_mutation(context, error)


async def submit_write(raft, store, command, context, deadline):
    try:
        await raft.wait_ready(remaining(deadline))
        index = await raft.propose(encode_command(command), remaining(deadline))
        await raft.wait_applied(index, remaining(deadline))
        outcome = store.get_outcome(index)
        if outcome.error_code:
            await context.abort(grpc.StatusCode[outcome.error_code], outcome.error_message)
        context.set_trailing_metadata(((APPLIED, str(index)),))
        return outcome
    except (sqlite3.Error, OverflowError) as error:
        raft._fail(error)
        await context.abort(grpc.StatusCode.INTERNAL, "Could not read the application outcome")
    except (NotLeaderError, TimeoutError, RuntimeError, grpc.RpcError) as error:
        await abort_mutation(context, error)
