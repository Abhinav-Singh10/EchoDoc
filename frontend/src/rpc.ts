import { createClient, } from '@connectrpc/connect'
import { createGrpcWebTransport } from '@connectrpc/connect-web'
import { SystemService } from './gen/collab/system/v1/system_pb'
import { AuthService } from './gen/collab/auth/v1/auth_pb'
import { DocumentService } from './gen/collab/document/v1/document_pb'

const baseUrl = import.meta.env.VITE_RPC_BASE_URL

if (!baseUrl) {
  throw new Error('VITE_RPC_BASE_URL is not configured')
}

// Transport object know the server add, and how to send grpc-web requests
const transport = createGrpcWebTransport({
  baseUrl,
})

// systemClient knows which RPCs exits and their req/res type
export const systemClient = createClient(SystemService, transport)

export const authClient = createClient(AuthService, transport)

export const documentClient = createClient(DocumentService, transport)