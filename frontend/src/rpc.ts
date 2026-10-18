import { createClient, } from '@connectrpc/connect'
import { createGrpcWebTransport } from '@connectrpc/connect-web'
import { SystemService } from './gen/collab/system/v1/system_pb'

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