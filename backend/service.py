import os #lets us read environment variables
import time #provides the clock we'll use to measure uptime
import uuid #genrates an identifier for this server run
import asyncio
import logging

from google.protobuf.timestamp_pb2 import Timestamp
from collab.system.v1 import system_pb2, system_pb2_grpc # this imports the generated message classes and RPC support. Our own code uses these files without editing them.

APPLICATION_VERSION = "0.1.0" # our chosen app version.
logger = logging.getLogger(__name__)

#The service class-> This declares our class and makes it inherit from the gen. SystemServiceServicer. 
# The gen. class provides method placeholders. We supply the actual behavior by implementing methods with same names (overiding a method basically)
class SystemService(system_pb2_grpc.SystemServiceServicer):

    #Whenever we start the server , we'll create one SystemService object and reuse it across requests.We won't create one per request
    def __init__(self): 
        self.server_id = os.environ.get("SERVER_ID", "app-1") #use env.var SERVER_ID or the default "app-1"
        self.process_instance_id = str(uuid.uuid4()) #create a random uuid4-> to string cause protobuff field is a string; Also creating it here means it stays the same across requests handled by this object. 
        #Creating it inside GetServerInfo would incorrectly give each request a new identifier

        # a monotonic clock cannot move backwards when the system calander clock is adjusted, making it suitable for measuring elapsed time
        self.started_at = time.monotonic() # We measure uptime from service initialization, which will happen during server startup

# This is the Request Handler
# async def declares a coroutine function for our async gRPC server
#request will contain the client's Empty message
# context provides the info and controls for this RPC, incl. cancellation and status
# We don;t need to use either param in this 1st handler, but they belong to its interface
# async handlers are supported by gRPC's AsyncIO server. async doesn't automatically create a thread or make blocking code nonblocking.This handler simply does a small amount of work and returns
    async def GetServerInfo(self, request, context):
        #contruct and return a generated protobuff message- not a python dictionary. the keyword args populate the fields we defined earlier in our .proto.
        return system_pb2.ServerInfo(
            server_id=self.server_id,
            process_instance_id=self.process_instance_id,
            application_version=APPLICATION_VERSION,
            uptime_seconds=time.monotonic() - self.started_at, # this experession is calcs the elapsed time in seconds
        )

    async def WatchEvents(self, request, context):
        subscription_id = str(uuid.uuid4()) # Distinguishes client calls
        sequence = 1 # number of response events. in the same call/sub

        logger.info("Stream started: subscription=%s", subscription_id)

        try:
            while True:
                timestamp = Timestamp() #Calander based
                timestamp.GetCurrentTime() #unaffected by calander clock

                # Using yeild instead of return cause its a responese stream 
                yield system_pb2.ServerEvent(
                    process_instance_id=self.process_instance_id,
                    sequence=sequence,
                    server_timestamp=timestamp,
                )

                sequence += 1
                await asyncio.sleep(1) # not the same as time.sleep(1) which blocks the event loop
        except Exception:
            logger.exception("Stream failed: subscription=%s", subscription_id)
            raise
        finally:
            logger.info("Stream ended: subscription=%s", subscription_id)