"""Fixed-membership Raft elections, log replication, and majority commitment."""

import asyncio
import logging
import random
import sqlite3
import time

import grpc

from backend.raft_commands import NoOpCommand, decode_command, encode_command
from collab.raft.v1 import raft_pb2, raft_pb2_grpc

logger = logging.getLogger(__name__)


class NotLeaderError(Exception):
    def __init__(self, leader_id):
        super().__init__(f"This node is not the Raft leader; known leader: {leader_id or 'unknown'}")
        self.leader_id = leader_id


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
        self.commit_index = 0
        self.next_index = {}
        self.match_index = {}
        self._pending = {}
        self.lock = asyncio.Lock()
        self._channels = {}
        self._clients = {}
        self._task = None
        self._stopping = False
        self._failure = None
        self._wake = asyncio.Event()
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
        self._fail_pending(RuntimeError("Raft node stopped"))
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        await asyncio.gather(*(channel.close() for channel in self._channels.values()))

    def _reset_deadline(self):
        self._election_deadline = time.monotonic() + random.uniform(*self.election_timeout)

    def _set_role(self, role, leader_id=""):
        self.role, self.leader_id = role, leader_id
        if role != "leader":
            self._fail_pending(NotLeaderError(leader_id))
            self.next_index.clear()
            self.match_index.clear()
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
        self._fail_pending(RuntimeError(f"Raft storage or background task failed: {error}"))
        self._wake.set()
        self._set_role("follower")

    def _fail_pending(self, error):
        for future in self._pending.values():
            if not future.done():
                future.set_exception(error)
        self._pending.clear()

    def _append_local(self, payload):
        try:
            index = self.store.last_log_position()[0] + 1
            self.store.append_entries([raft_pb2.LogEntry(index=index, term=self.term, command=payload)])
            self.match_index[self.node_id] = index
            return index
        except (sqlite3.Error, OverflowError) as error:
            self._fail(error)
            raise

    def _become_leader(self):
        if self.role == "leader":
            return
        # Initialize from the old tail so the first round includes the new no-op.
        last_index = self.store.last_log_position()[0]
        self._set_role("leader", self.node_id)
        self.next_index = {peer: last_index + 1 for peer in self.members if peer != self.node_id}
        self.match_index = {peer: 0 for peer in self.members}
        self._append_local(encode_command(NoOpCommand()))
        self._advance_commit()
        self._next_heartbeat = 0
        self._wake.set()

    def _set_commit_index(self, index):
        if index <= self.commit_index:
            return
        self.commit_index = index
        for pending_index in list(self._pending):
            if pending_index <= index:
                future = self._pending.pop(pending_index)
                if not future.done():
                    future.set_result(pending_index)
        if self.role == "leader":
            self._next_heartbeat = 0
            self._wake.set()

    def _advance_commit(self):
        if self.role != "leader":
            return
        index = sorted(self.match_index.values(), reverse=True)[self.majority - 1]
        if index > self.commit_index:
            try:
                entry = self.store.get_entry(index)
                if entry is not None and entry.term == self.term:
                    self._set_commit_index(index)
            except (sqlite3.Error, OverflowError) as error:
                self._fail(error)
                raise

    async def propose(self, command_bytes, timeout=5.0):
        if timeout <= 0:
            raise ValueError("Proposal timeout must be positive")
        future = None
        index = None
        try:
            async with self.lock:
                if self._failure is not None or self._stopping:
                    raise RuntimeError("Raft node is unavailable")
                if self.role != "leader":
                    raise NotLeaderError(self.leader_id)
                decode_command(command_bytes)
                index = self._append_local(command_bytes)
                future = asyncio.get_running_loop().create_future()
                self._pending[index] = future
                self._advance_commit()
                self._next_heartbeat = 0
                self._wake.set()
            return await asyncio.wait_for(future, timeout)
        finally:
            if future is not None:
                if self._pending.get(index) is future:
                    self._pending.pop(index)
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()  # Retrieve failures even if persistence raised before waiting.

    async def get_status(self):
        async with self.lock:
            try:
                return {
                    "raft_role": self.role, "raft_term": self.term,
                    "raft_leader_id": self.leader_id,
                    "raft_last_log_index": self.store.last_log_position()[0],
                    "raft_commit_index": self.commit_index,
                }
            except (sqlite3.Error, OverflowError) as error:
                self._fail(error)
                raise

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
                if request.term < self.term:
                    return raft_pb2.AppendEntriesResponse(term=self.term, success=False)
                # Validate the whole batch before writing even its first entry.
                previous_term = request.prev_log_term
                for index, entry in enumerate(request.entries, start=request.prev_log_index + 1):
                    if entry.index != index or not 0 < entry.term <= request.term or entry.term < previous_term:
                        await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid Raft log batch")
                    previous_term = entry.term
                self._set_role("follower", request.leader_id)
                self._reset_deadline()
                if request.prev_log_index == 0:
                    matches = request.prev_log_term == 0
                else:
                    previous = self.store.get_entry(request.prev_log_index)
                    matches = previous is not None and previous.term == request.prev_log_term
                if not matches:
                    return raft_pb2.AppendEntriesResponse(term=self.term, success=False)
                replacement = None
                for offset, entry in enumerate(request.entries):
                    existing = self.store.get_entry(entry.index)
                    if existing is None or existing.term != entry.term:
                        if entry.index <= self.commit_index:
                            await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Cannot replace a committed entry")
                        if replacement is None:
                            replacement = offset
                    elif existing.command != entry.command:
                        await context.abort(grpc.StatusCode.FAILED_PRECONDITION, "Command differs at the same index and term")
                if replacement is not None:
                    suffix = request.entries[replacement:]
                    self.store.replace_suffix(suffix[0].index, suffix)
                matched_index = request.prev_log_index + len(request.entries)
                self._set_commit_index(min(request.leader_commit, matched_index))
                return raft_pb2.AppendEntriesResponse(term=self.term, success=True, match_index=matched_index)
            except (sqlite3.Error, OverflowError) as error:
                self._fail(error)
                await context.abort(grpc.StatusCode.INTERNAL, "Could not read or persist Raft state/log")

    async def _run(self):
        try:
            while not self._stopping:
                self._wake.clear()
                if self._failure is not None:
                    raise RuntimeError("Raft storage failed") from self._failure
                await self._tick()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self.tick_interval)
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
                    self._become_leader()
            else:
                return
        if request is not None and self.majority > 1:
            await self._request_votes(request)
        await self._replicate()

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
                            self._become_leader()
                            return
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _replicate(self):
        async with self.lock:
            if self._failure is not None or self._stopping or self.role != "leader":
                return
            if time.monotonic() < self._next_heartbeat:
                return
            self._next_heartbeat = time.monotonic() + self.heartbeat_interval
        tasks = [asyncio.create_task(self._replicate_peer(peer)) for peer in self._clients]
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _replicate_peer(self, peer):
        try:
            async with self.lock:
                if self.role != "leader" or self._failure is not None or self._stopping:
                    return
                next_index = self.next_index[peer]
                previous = self.store.get_entry(next_index - 1) if next_index > 1 else None
                request = raft_pb2.AppendEntriesRequest(
                    term=self.term, leader_id=self.node_id,
                    prev_log_index=next_index - 1, prev_log_term=previous.term if previous else 0,
                    entries=self.store.read_entries(next_index, limit=64),
                    leader_commit=self.commit_index,
                )
            _, response = await self._call_peer(peer, "AppendEntries", request)
            if response is None:
                return
            async with self.lock:
                if (self.role != "leader" or self.term != request.term or response.term != self.term
                        or self._failure is not None or self._stopping):
                    return
                matched_index = request.prev_log_index + len(request.entries)
                if response.success:
                    if response.match_index != matched_index:
                        return  # Acknowledge only the range this request actually sent.
                    self.match_index[peer] = max(self.match_index[peer], matched_index)
                    self.next_index[peer] = max(self.next_index[peer], matched_index + 1)
                    self._advance_commit()
                    if self.next_index[peer] <= self.store.last_log_position()[0]:
                        self._next_heartbeat = 0
                        self._wake.set()
                elif self.next_index[peer] == next_index:
                    self.next_index[peer] = max(1, self.match_index[peer] + 1, next_index - 1)
                    if self.next_index[peer] < next_index:
                        self._next_heartbeat = 0
                        self._wake.set()
        except (sqlite3.Error, OverflowError) as error:
            self._fail(error)
            raise

