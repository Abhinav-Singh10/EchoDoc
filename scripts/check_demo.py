"""Focused RPC check against deploy/demo.json; creates a separate test note."""
import asyncio
import json
from pathlib import Path
import uuid
import grpc
from google.protobuf.empty_pb2 import Empty
from pycrdt import Doc, Text
from collab.auth.v1 import auth_pb2 as auth, auth_pb2_grpc as auth_rpc
from collab.document.v1 import document_pb2 as doc, document_pb2_grpc as doc_rpc
from collab.ai.v1 import ai_pb2 as ai, ai_pb2_grpc as ai_rpc


async def rejected(call, code):
    try:
        await call
    except grpc.aio.AioRpcError as error:
        assert error.code() == code, error
    else:
        raise AssertionError(f'Expected {code.name}')


async def main():
    config = json.loads((Path(__file__).resolve().parents[1] / 'deploy/demo.json').read_text())
    async with grpc.aio.insecure_channel(f"127.0.0.1:{config['app_port']}") as channel:
        accounts = auth_rpc.AuthServiceStub(channel)
        documents = doc_rpc.DocumentServiceStub(channel)
        writing = ai_rpc.WritingServiceStub(channel)
        login = await accounts.Login(auth.LoginRequest(username='alice', password='demo1234'), timeout=5)
        options = {'metadata': (('authorization', f'Bearer {login.session_token}'),), 'timeout': 5}
        try:
            await rejected(documents.ListDocuments(Empty(), timeout=5), grpc.StatusCode.UNAUTHENTICATED)
            created = await documents.CreateDocument(doc.CreateDocumentRequest(title='RPC smoke check'), **options)
            local = Doc({'content': Text('The team are building a shared editor. It save notes.')})
            request = doc.SubmitUpdateRequest(document_id=created.document_id,
                request_id=str(uuid.uuid4()), update=local.get_update())
            first, repeated = await asyncio.gather(documents.SubmitUpdate(request, **options),
                                                   documents.SubmitUpdate(request, **options))
            loaded = await documents.GetDocument(doc.GetDocumentRequest(document_id=created.document_id), **options)
            assert first.revision == repeated.revision == loaded.document.revision == 1
            replica = Doc(); replica.apply_update(loaded.state)
            assert str(replica.get('content', type=Text)) == str(local.get('content', type=Text))
            print('PASS: authenticated persistence and concurrent duplicate requests')
            for action in (ai.GRAMMAR, ai.SUGGEST, ai.SUMMARIZE, ai.ENHANCE):
                query = ai.AnswerRequest(document_id=created.document_id, request_id=str(uuid.uuid4()),
                    source_revision=1, action=action, text=str(local.get('content', type=Text)))
                answer = await writing.GetLLMAnswer(query, metadata=options['metadata'], timeout=50)
                assert answer.answer.strip() and answer.source_revision == 1
                assert answer.request_id == query.request_id
                print(f'PASS: {ai.Action.Name(action)} returned a local model result')
            query.source_revision = 0
            await rejected(writing.GetLLMAnswer(query, **options), grpc.StatusCode.FAILED_PRECONDITION)
            query.source_revision = 1; query.action = ai.ACTION_UNSPECIFIED
            await rejected(writing.GetLLMAnswer(query, **options), grpc.StatusCode.INVALID_ARGUMENT)
            print('PASS: stale revision and invalid action rejected')
        finally:
            await accounts.Logout(Empty(), **options)
        await rejected(accounts.GetCurrentUser(Empty(), **options), grpc.StatusCode.UNAUTHENTICATED)
        print('PASS: logged-out session rejected')


if __name__ == '__main__':
    asyncio.run(main())
