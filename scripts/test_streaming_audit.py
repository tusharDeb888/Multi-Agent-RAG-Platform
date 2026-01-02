"""
Test Streaming Audit Logic (Mock).
"""
import asyncio
import json
from unittest.mock import MagicMock, AsyncMock
from app.application.api.chat import chat_stream, ChatRequest

async def test_streaming_audit():
    print("Testing Streaming Audit Logic...")
    
    # Mocks
    mock_request = MagicMock()
    mock_body = ChatRequest(query="Test Query", top_k=5)
    mock_user = MagicMock(id=123)
    
    # Mock RAG Service
    mock_rag = MagicMock()
    
    # Async generator for RAG stream
    async def mock_stream_gen(*args, **kwargs):
        yield f"data: {json.dumps({'status': 'Thinking'})}\n\n"
        yield f"data: {json.dumps({'token': 'Hello '})}\n\n"
        yield f"data: {json.dumps({'token': 'World'})}\n\n"
        yield f"data: {json.dumps({'citations': [{'document_id': 101, 'document_name': 'test.pdf'}]})}\n\n"
        yield "data: [DONE]\n\n"
        
    mock_rag.stream_query = mock_stream_gen
    
    # Mock Audit Service
    mock_audit = MagicMock()
    
    # Call the endpoint handler
    response = await chat_stream(
        request=mock_request,
        body=mock_body,
        current_user=mock_user,
        rag_service=mock_rag,
        audit_service=mock_audit
    )
    
    # Consume the streaming response
    # StreamingResponse.body_iterator is the generator
    print("Consuming stream...")
    async for chunk in response.body_iterator:
        # print(f"Received: {chunk}")
        pass
        
    print("Stream finished.")
    
    # Verify Audit Log was called with FULL text
    mock_audit.log_query.assert_called_once()
    call_args = mock_audit.log_query.call_args[1] # kwargs
    
    print("\nAudit Log Capture:")
    print(f"User ID: {call_args['user_id']}")
    print(f"Query: {call_args['query_text']}")
    print(f"Response: {call_args['response_text']}")
    print(f"Docs: {call_args['accessed_document_ids']}")
    
    # Assertions
    assert call_args['user_id'] == 123
    assert call_args['response_text'] == "Hello World"
    assert call_args['accessed_document_ids'] == [101]
    
    print("\n✅ Streaming Audit Verified Success!")

if __name__ == "__main__":
    asyncio.run(test_streaming_audit())
