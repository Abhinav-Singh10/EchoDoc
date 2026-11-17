"""Fixed-membership Raft elections and empty heartbeats; replication comes later."""

import asyncio
import logging
import random
import sqlite3
import time

import grpc

from collab.raft.v1 import raft_pb2, raft_pb2_grpc

logger = logging.getLogger(__name__)


class RaftNode(raft_pb2_grpc.RaftServiceServicer):
    def __init__(self, node_id, members, store, *, election_timeout=(1.5, 3.0),
                 heartbeat_interval=0.25, rpc_timeout=0.4, tick_interval=0.05):
        if not isinstance(members, dict) or not members or node_id not in members:
            raise ValueError("Raft membership must contain this node's SERVER_ID")
        if any(not isinstance(key, str) or not key.strip() for key in members):
            raise ValueError("Raft member IDs must be nonempty strings")
        addresses = list(members.values())
        if any(not isinstance(address, str) or not address.strip() for address in addresses):
            raise ValueError("Raft member addresses must be nonempty strings")
        if len(set(addresses)) != len(addresses):
            raise ValueError("Raft member addresses must be distinct")
        if not 0 < election_timeout[0] <= election_timeout[1] or min(
            heartbeat_interval, rpc_timeout, tick_interval,
        ) <= 0:
            raise ValueError("Raft timing values must be positive and election bounds ordered")

        self.node_id = node_id
        self.members = dict(members)
        self.store = store
        self.majority = len(members) // 2 + 1
        self.election_timeout = election_timeout
        self.heartbeat_interval = heartbeat_interval
        self.rpc_timeout = rpc_timeout
        self.tick_interval = tick_interval
        state = store.get_state()
        self.term = state["current_term"]
        self.voted_for = state["voted_for"]
        self.role = "follower"
        self.leader_id = ""
        self.lock = asyncio.Lock()
        self._channels = {}
        self._clients = {}
        self._task = None
        self._stopping = False
        self._failure = None
        self._failed = asyncio.Event()
        self._last_status = None
        self._next_heartbeat = 0
        self._reset_deadline()
        self._set_role("follower")

    def start(self):
        if self._task is not None:
            raise RuntimeError("Raft node has already been started")
        for peer, address in self.members.items():
            if peer != self.node_id:
                channel = grpc.aio.insecure_channel(address)
                self._channels[peer] = channel
                self._clients[peer] = raft_pb2_grpc.RaftServiceStub(channel)
        self._reset_deadline()
        self._task = asyncio.create_task(self._run(), name=f"raft-{self.node_id}")
        return self._task

    async def stop(self):
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        await asyncio.gather(*(channel.close() for channel in self._channels.values()))

    def _reset_deadline(self):
        self._election_deadline = time.monotonic() + random.uniform(*self.election_timeout)

    def _set_role(self, role, leader_id=""):
        self.role, self.leader_id = role, leader_id
        status = (role, self.term, leader_id)
        if status != self._last_status:
            logger.info("Raft %s: role=%s term=%s leader=%s", self.node_id,
                        role, self.term, leader_id or "unknown")
            self._last_status = status

    def _save_state(self, term, voted_for):
        # Update memory only after SQLite has committed the term and vote.
        try:
            self.store.save_state(term, voted_for)
        except (sqlite3.Error, OverflowError) as error:
            # A concurrent peer reply may fail after another reply wins a vote.
            # Mark failure here even if the caller cancels that completed round.
            self._fail(error)
            raise
        self.term, self.voted_for = term, voted_for

    def _adopt_term(self, term):
        if term > self.term:
            self._save_state(term, None)
            self._set_role("follower")

    def _fail(self, error):
        self._failure = error
        self._failed.set()
        self._set_role("follower")

    async def _check_available(self, context):
        if self._failure is not None or self._stopping:
            await context.abort(grpc.StatusCode.UNAVAILABLE, "Raft node is stopping")

    async def RequestVote(self, request, context):
        async with self.lock:
            await self._check_available(context)
            if request.candidate_id not in self.members:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Unknown Raft candidate")
            try:
                self._adopt_term(request.term)
                granted = False
                if request.term == self.term:
                    last_index, last_term = self.store.last_log_position()
                    up_to_date = (request.last_log_term, request.last_log_index) >= (last_term, last_index)
                    if up_to_date and self.voted_for in (None, request.candidate_id):
                        self._save_state(self.term, request.candidate_id)
                        self._reset_deadline()
                        granted = True
                return raft_pb2.RequestVoteResponse(term=self.term, vote_granted=granted)
            except (sqlite3.Error, OverflowError) as error:
                self._fail(error)
                await context.abort(grpc.StatusCode.INTERNAL, "Could not persist Raft state")

    async def AppendEntries(self, request, context):
        async with self.lock:
            await self._check_available(context)
            if request.leader_id not in self.members:
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Unknown Raft leader")
            try:
                self._adopt_term(request.term)
                if request.entries or request.leader_commit:
                    await context.abort(grpc.StatusCode.UNIMPLEMENTED, "Raft replication is not implemented yet")
                if request.term < self.term:
                    return raft_pb2.AppendEntriesResponse(term=self.term, success=False)
                self._set_role("follower", request.leader_id)
                self._reset_deadline()
                if request.prev_log_index == 0:
                    matches = request.prev_log_term == 0
                else:
                    previous = self.store.get_entry(request.prev_log_index)
                    matches = previous is not None and previous.term == request.prev_log_term
                return raft_pb2.AppendEntriesResponse(
                    term=self.term, success=matches,
                    match_index=request.prev_log_index if matches else 0,
                )
            except (sqlite3.Error, OverflowError) as error:
                self._fail(error)
                await context.abort(grpc.StatusCode.INTERNAL, "Could not read or persist Raft state")

    async def _run(self):
        try:
            while not self._stopping:
                if self._failure is not None:
                    raise RuntimeError("Raft storage failed") from self._failure
                await self._tick()
                try:
                    await asyncio.wait_for(self._failed.wait(), timeout=self.tick_interval)
                except TimeoutError:
                    pass
        except Exception as error:
            self._fail(error)
            logger.exception("Raft %s stopped after an error", self.node_id)
            raise

    async def _tick(self):
        async with self.lock:
            if self._failure is not None:
                raise RuntimeError("Raft storage failed") from self._failure
            if self.role == "leader":
                request = None
            elif time.monotonic() >= self._election_deadline:
                self._save_state(self.term + 1, self.node_id)
                self._set_role("candidate")
                self._reset_deadline()
                last_index, last_term = self.store.last_log_position()
                request = raft_pb2.RequestVoteRequest(
                    term=self.term, candidate_id=self.node_id,
                    last_log_index=last_index, last_log_term=last_term,
                )
                if self.majority == 1:
                    self._set_role("leader", self.node_id)
                    self._next_heartbeat = 0
            else:
                return
        if request is not None and self.majority > 1:
            await self._request_votes(request)
        await self._send_heartbeats()

    async def _call_peer(self, peer, method, request):
        try:
            response = await getattr(self._clients[peer], method)(request, timeout=self.rpc_timeout)
        except grpc.RpcError:
            return peer, None
        async with self.lock:
            if self._failure is not None or self._stopping:
                return peer, None
            # Even a reply to an old round can teach us about a newer term.
            self._adopt_term(response.term)
        return peer, response

    async def _request_votes(self, request):
        tasks = [asyncio.create_task(self._call_peer(peer, "RequestVote", request))
                 for peer in self._clients]
        votes = {self.node_id}
        try:
            for completed in asyncio.as_completed(tasks):
                peer, response = await completed
                if response is None:
                    continue
                async with self.lock:
                    if self._failure is not None or self._stopping:
                        return
                    if self.term != request.term or self.role != "candidate":
                        return
                    if response.term == request.term and response.vote_granted:
                        votes.add(peer)
                        if len(votes) >= self.majority:
                            self._set_role("leader", self.node_id)
                            self._next_heartbeat = 0
                            return
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_heartbeats(self):
        async with self.lock:
            if self._failure is not None or self._stopping or self.role != "leader":
                return
            if time.monotonic() < self._next_heartbeat:
                return
            self._next_heartbeat = time.monotonic() + self.heartbeat_interval
            last_index, last_term = self.store.last_log_position()
            request = raft_pb2.AppendEntriesRequest(
                term=self.term, leader_id=self.node_id,
                prev_log_index=last_index, prev_log_term=last_term, leader_commit=0,
            )
        tasks = [asyncio.create_task(self._call_peer(peer, "AppendEntries", request))
                 for peer in self._clients]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

