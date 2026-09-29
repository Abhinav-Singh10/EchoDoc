import { createClient, } from '@connectrpc/connect'
import { createGrpcWebTransport } from '@connectrpc/connect-web'
import { AuthService } from './gen/collab/auth/v1/auth_pb'
import { WritingService } from './gen/collab/ai/v1/ai_pb'
import { DocumentService } from './gen/collab/document/v1/document_pb'

const baseUrl = import.meta.env.VITE_RPC_BASE_URL || `${window.location.origin}/rpc`

// Transport object know the server add, and how to send grpc-web requests
const transport = createGrpcWebTransport({
  baseUrl,
})

export const authClient = createClient(AuthService, transport)

export const documentClient = createClient(DocumentService, transport)

export const writingClient = createClient(WritingService, transport)
