import os
import time
import uuid
import asyncio
import logging

import grpc
from google.protobuf.empty_pb2 import Empty
from google.protobuf.timestamp_pb2 import Timestamp

from collab.system.v1 import system_pb2, system_pb2_grpc

APPLICATION_VERSION = "0.1.0"
logger = logging.getLogger(__name__)


class SystemService(system_pb2_grpc.SystemServiceServicer):

    def __init__(self, raft_node=None):
        self.raft_node = raft_node
        self.server_id = raft_node.node_id if raft_node else os.environ.get("SERVER_ID", "app-1")
        self.process_instance_id = str(uuid.uuid4())
        self.started_at = time.monotonic()

    async def GetServerInfo(self, request, context):
        status = await self.raft_node.get_status() if self.raft_node else {"raft_role": "disabled"}
        return system_pb2.ServerInfo(
            server_id=self.server_id,
            process_instance_id=self.process_instance_id,
            application_version=APPLICATION_VERSION,
            uptime_seconds=time.monotonic() - self.started_at,
            **status,
        )

    async def GetClusterInfo(self, request, context):
        # This is diagnostic fan-out, not a Raft read barrier or a quorum check.
        members = self.raft_node.members if self.raft_node else {self.server_id: None}
        remaining = context.time_remaining()
        timeout = min(1.0, remaining) if remaining is not None else 1.0

        async def inspect(node_id, address):
            def failed(code, message):
                return system_pb2.ClusterNodeStatus(
                    node_id=node_id, error=system_pb2.NodeStatusError(code=code, message=message),
                )

            try:
                async with asyncio.timeout(timeout):
                    if node_id == self.server_id:
                        info = await self.GetServerInfo(Empty(), context)
                    else:
                        async with grpc.aio.insecure_channel(address) as channel:
                            info = await system_pb2_grpc.SystemServiceStub(channel).GetServerInfo(
                                Empty(), timeout=timeout,
                            )
                    if info.server_id != node_id:
                        return failed("FAILED_PRECONDITION", "Configured node ID differs from the responding server")
                    return system_pb2.ClusterNodeStatus(node_id=node_id, info=info)
            except TimeoutError:
                return failed("DEADLINE_EXCEEDED", "Node status check timed out")
            except grpc.RpcError as error:
                return failed(error.code().name, error.details())
            except Exception:
                logger.exception("Could not inspect status for %s", node_id)
                return failed("INTERNAL", "Could not read node status; inspect backend logs")

        nodes = await asyncio.gather(*(inspect(node_id, address) for node_id, address in sorted(members.items())))
        return system_pb2.ClusterInfo(responding_server_id=self.server_id, nodes=nodes)

    async def WatchEvents(self, request, context):
        subscription_id = str(uuid.uuid4()) 
        sequence = 1 

        logger.info("Stream started: subscription=%s", subscription_id)

        try:
            while True:
                timestamp = Timestamp() 
                timestamp.GetCurrentTime()

                yield system_pb2.ServerEvent(
                    process_instance_id=self.process_instance_id,
                    sequence=sequence,
                    server_timestamp=timestamp,
                )

                sequence += 1
                await asyncio.sleep(
                    1
                )
        except Exception:
            logger.exception("Stream failed: subscription=%s", subscription_id)
            raise
        finally:
            logger.info("Stream ended: subscription=%s", subscription_id)
