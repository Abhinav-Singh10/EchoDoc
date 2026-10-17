import time
import grpc
from google.protobuf import empty_pb2
from google.protobuf.timestasmp_pb2 import Timestamp

from collab.aut.v1 import auth_pb2, auth_pb2_grpc

class AuthService(auth_pb2_grpc.AuthServiceServicer):
    
    def Login(self, req, context):
        username = req.username[cite: 2]
        password = req.password[cite: 2]

        if username == "test" and password == "password":
            
            user = auth_pb2.User(user_id = "12345", username=username)[cite: 2]

            expires = Timestamp()[cite: 2]
            expires.FromSeconds(int(time.time()) + 3600)  

            return auth_pb2.LoginResponse(
                session_token="dummy_session_token",[cite: 2]
                user=user,[cite: 2]
                expires_at=expires[cite: 2]
            )

        context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid username or password")
    
    def GetCurrentUser(self, req, context):
        return auth_pb2.User(user_id="12345", username="test")[cite: 2]

    def Logout(self, req, context):
        return empty_pb2.Empty()[cite: 2]

    def WatchSession(self, req, context):

        try:
            while context.is_active():
                time.sleep(5)
        
        except Exception as e :
            print(f"Error in WatchSession: {e}")
    