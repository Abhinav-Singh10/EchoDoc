import os
import time
import uuid
import asyncio
import logging

from google.protobuf.timestamp_pb2 import Timestamp

from collab.system.v1 import system_pb2, system_pb2_grpc

APPLICATION_VERSION = "0.1.0"
logger = logging.getLogger(__name__)


class SystemService(system_pb2_grpc.SystemServiceServicer):

    def __init__(self):
        self.server_id = os.environ.get("SERVER_ID", "app-1")
        self.process_instance_id = str(uuid.uuid4())
        self.started_at = time.monotonic()

    async def GetServerInfo(self, request, context):

        return system_pb2.ServerInfo(
            server_id=self.server_id,
            process_instance_id=self.process_instance_id,
            application_version=APPLICATION_VERSION,
            uptime_seconds=time.monotonic() - self.started_at,
        )

    async def WatchEvents(self, request, context):
        subscription_id = str(uuid.uuid4())  # Distinguishes client calls
        sequence = 1  # number of req. in the same call

        logger.info("Stream started: subscription=%s", subscription_id)

        try:
            while True:
                timestamp = Timestamp()  # Calander based
                timestamp.GetCurrentTime()  # Monotonic, unaffected by calander clock

                # Using yeild instead of return cause its a responese stream
                yield system_pb2.ServerEvent(
                    process_instance_id=self.process_instance_id,
                    sequence=sequence,
                    server_timestamp=timestamp,
                )

                sequence += 1
                await asyncio.sleep(
                    1
                )  # not the same as time.sleep(1) which blocks the event loop
        except Exception:
            logger.exception("Stream failed: subscription=%s", subscription_id)
            raise
        finally:
            logger.info("Stream ended: subscription=%s", subscription_id)
