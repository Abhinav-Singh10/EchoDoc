# Collaborative System Project

An Advanced Operating Systems course project.

## Iteration 1

Build and verify browser-to-Python communication using unary
and server-streaming RPCs.

## Planned architecture

- Frontend: React and TypeScript.
- Gateway: Envoy translates gRPC-Web into native gRPC.
- Backend: Python implements the gRPC service.
- Deployment: Docker Compose runs the three services.