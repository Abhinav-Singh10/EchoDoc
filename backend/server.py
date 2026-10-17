import grpc
import logging
from concurrent import futures

from collab.aut.v1 import auth_pb2_grpc
from auth_service import AuthService

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthService(), server)
    
    server.add_insecure_port('[::]:50051')
    server.start()
    logging.info("Auth service started on port 50051")
    server.wait_for_termination()

if __name__ == '__main__':
    logging.basicConfig()
    serve()