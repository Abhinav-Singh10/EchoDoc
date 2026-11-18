import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import socket
import sys
import time
from types import SimpleNamespace

import grpc
from argon2 import PasswordHasher
from google.protobuf.empty_pb2 import Empty

from collab.auth.v1 import auth_pb2_grpc
from collab.document.v1 import document_pb2_grpc
from collab.system.v1 import system_pb2_grpc

ROOT = Path(__file__).resolve().parents[1]


def check_backend_setup(config):
    if not Path(config["users"]).is_file():
        raise ValueError("Missing temporary accounts")
    for service in ("auth", "document", "system", "ai", "raft"):
        if not (ROOT / f"backend/generated/collab/{service}/v1/{service}_pb2_grpc.py").is_file():
            raise ValueError("Missing Python RPC definitions. Run python scripts/generate_protos.py.")


class LocalCluster:
    def __init__(self, root, node_ids=("app-1", "app-2", "app-3"), *, usernames=("alice",), verbose=False):
        self.root, self.nodes = root, {}
        self.verbose = verbose
        self.channels = []
        with ExitStack() as stack:
            sockets = [stack.enter_context(socket.socket()) for _ in range(len(node_ids) + 3)]
            for probe in sockets:
                probe.bind(("127.0.0.1", 0))
            ports = [probe.getsockname()[1] for probe in sockets]
        users = root / "users.json"
        password_hash = PasswordHasher().hash("test-password")
        users.write_text(json.dumps({name: {
            "user_id": f"user-{name}", "username": name, "password_hash": password_hash,
        } for name in usernames}))
        self.config = {
            "nodes": [{"id": node_id, "app_port": port, "database": str(root / f"{node_id}.sqlite3")}
                      for node_id, port in zip(node_ids, ports)],
            "users": str(users), "ai_port": ports[-3], "gateway_port": ports[-2], "frontend_port": ports[-1],
        }
        (root / "cluster.json").write_text(json.dumps(self.config))
        check_backend_setup(self.config)
        self.generation = 0

    def database(self, node_id):
        return self.root / f"{node_id}.sqlite3"

    async def start_node(self, node_id, *, restart=False, command=None, on_line=None, wait=True):
        config_node = next(node for node in self.config["nodes"] if node["id"] == node_id)
        if restart and not self.database(node_id).is_file():
            raise ValueError(f"No existing recovery database for {node_id}")
        environment = dict(
            os.environ, PYTHONPATH=str(ROOT / "backend/generated"),
            SERVER_ID=node_id, APP_BIND=f"127.0.0.1:{config_node['app_port']}",
            DATABASE_PATH=str(self.database(node_id)), USERS_PATH=self.config["users"],
            AI_ADDRESS=f"127.0.0.1:{self.config['ai_port']}",
            RAFT_MEMBERS=json.dumps({node["id"]: f"127.0.0.1:{node['app_port']}" for node in self.config["nodes"]}),
        )
        if command is None:
            command = [sys.executable, "-B", "-u", "-m", "backend.server"]
        environment["PYTHONPATH"] += os.pathsep + str(ROOT)
        self.generation += 1
        log_path = self.root / f"{node_id}-{self.generation}.log"
        process = await asyncio.create_subprocess_exec(
            *command, cwd=ROOT, env=environment, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, start_new_session=True,
        )
        channel = grpc.aio.insecure_channel(environment["APP_BIND"])
        self.channels.append(channel)
        node = SimpleNamespace(
            node_id=node_id, process=process, channel=channel, log_path=log_path,
            auth=auth_pb2_grpc.AuthServiceStub(channel), docs=document_pb2_grpc.DocumentServiceStub(channel),
            system=system_pb2_grpc.SystemServiceStub(channel),
        )

        async def collect_output():
            with log_path.open("w") as log:
                async for raw in process.stdout:
                    line = raw.decode(errors="replace")
                    log.write(line)
                    log.flush()
                    if on_line is not None:
                        on_line(line)

        node.reader = asyncio.create_task(collect_output())
        self.nodes[node_id] = node
        if self.verbose:
            print(f"{node_id}: PID {process.pid}, {environment['APP_BIND']}, log {log_path}", flush=True)
        if wait:
            connected = asyncio.create_task(channel.channel_ready())
            exited = asyncio.create_task(process.wait())
            try:
                done, _ = await asyncio.wait((connected, exited), timeout=30, return_when=asyncio.FIRST_COMPLETED)
                if connected not in done or exited in done or process.returncode is not None:
                    raise AssertionError(f"Backend {node_id} did not start: {log_path.read_text()}")
            finally:
                connected.cancel()
                exited.cancel()
                await asyncio.gather(connected, exited, return_exceptions=True)
        return node

    async def start_all(self):
        results = await asyncio.gather(*(self.start_node(node["id"]) for node in self.config["nodes"]), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return await self.ready()

    async def statuses(self):
        ids = list(self.nodes)
        nodes = [self.nodes[node_id] for node_id in ids]
        infos = await asyncio.gather(*(node.system.GetServerInfo(Empty(), timeout=0.5)
                                       for node in nodes), return_exceptions=True)
        return {node_id: info for node_id, info in zip(ids, infos) if not isinstance(info, BaseException)}

    async def ready(self, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for node in self.nodes.values():
                if node.process.returncode is not None:
                    raise RuntimeError(f"Backend {node.node_id} exited: {node.log_path}")
            infos = await self.statuses()
            leaders = [info for info in infos.values() if info.raft_role == "leader"]
            if len(infos) == len(self.nodes) and len(leaders) == 1:
                leader = leaders[0]
                if leader.raft_commit_index > 0 and leader.raft_last_applied >= leader.raft_commit_index and all(
                    info.raft_term == leader.raft_term and info.raft_leader_id == leader.server_id
                    for info in infos.values()
                ):
                    return self.nodes[leader.server_id]
            await asyncio.sleep(0.05)
        raise AssertionError(f"Cluster failed to settle: {infos}")

    async def applied(self, index, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            infos = await self.statuses()
            if len(infos) == len(self.nodes) and all(info.raft_last_applied >= index for info in infos.values()):
                return
            await asyncio.sleep(0.02)
        raise AssertionError(f"Nodes did not apply through {index}: {infos}")

    async def stop_node(self, node_id, stop_signal=signal.SIGKILL):
        node = self.nodes.pop(node_id)
        if node.process.returncode is None:
            try:
                node.process.send_signal(stop_signal)
            except ProcessLookupError:
                pass
        await asyncio.wait_for(node.process.wait(), 8)
        await node.reader
        return node.process.returncode

    async def close(self):
        for node in self.nodes.values():
            if node.process.returncode is None:
                try:
                    node.process.kill()
                except ProcessLookupError:
                    pass
        await asyncio.gather(*(self.stop_node(node_id) for node_id in list(self.nodes)))
        await asyncio.gather(*(channel.close() for channel in self.channels))
        self.channels.clear()

