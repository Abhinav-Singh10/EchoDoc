import os 
import time 
import uuid 
 
from collab.system.v1 import system_pb2, system_pb2_grpc 

APPLICATION_VERSION = "0.1.0" 
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