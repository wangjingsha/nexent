import pytest
import sys
import os

# Dynamically determine the backend path
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, "../../../backend"))
sys.path.append(backend_dir)

# Mock external dependencies before importing the modules that use them
sys.modules['database.client'] = pytest.importorskip("unittest.mock").MagicMock()
sys.modules['database.agent_db'] = pytest.importorskip("unittest.mock").MagicMock()
sys.modules['agents.create_agent_info'] = pytest.importorskip("unittest.mock").MagicMock()
sys.modules['nexent.core.agents.run_agent'] = pytest.importorskip("unittest.mock").MagicMock()

# Now it's safe to import the modules we need to test
from fastapi.testclient import TestClient
from fastapi import HTTPException
from fastapi import FastAPI
from backend.apps.agent_app import router

# Create FastAPI app for testing
app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture
def mock_auth_header():
    return {"Authorization": "Bearer test_token"}


@pytest.fixture
def mock_conversation_id():
    return 123


@pytest.mark.asyncio
async def test_agent_run_api_success(mocker, mock_auth_header, mock_conversation_id):
    # Setup mocks using pytest-mock
    mock_get_user_info = mocker.patch("backend.apps.agent_app.get_current_user_info")
    mock_create_run_info = mocker.patch("backend.apps.agent_app.create_agent_run_info", new_callable=mocker.AsyncMock)
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run = mocker.patch("backend.apps.agent_app.agent_run")
    mock_submit = mocker.patch("backend.apps.agent_app.submit")
    
    mock_get_user_info.return_value = ("user_id", "email", "en")
    mock_create_run_info.return_value = mocker.MagicMock()
    
    # Create a real async generator to mock agent_run
    async def mock_async_generator():
        for chunk in ["chunk1", "chunk2"]:
            yield chunk
    
    mock_agent_run.return_value = mock_async_generator()
    
    # Test the endpoint
    response = client.post(
        "/agent/run",
        json={
            "agent_id": 123,
            "conversation_id": mock_conversation_id,
            "query": "test query",
            "history": [],
            "minio_files": [],
            "is_debug": False
        },
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_agent_run_manager.register_agent_run.assert_called_once()
    mock_submit.assert_called()
    mock_agent_run_manager.unregister_agent_run.assert_called_once_with(mock_conversation_id)


@pytest.mark.asyncio
async def test_agent_run_api_debug_mode(mocker, mock_auth_header, mock_conversation_id):
    # Setup mocks using pytest-mock
    mock_get_user_info = mocker.patch("backend.apps.agent_app.get_current_user_info")
    mock_create_run_info = mocker.patch("backend.apps.agent_app.create_agent_run_info", new_callable=mocker.AsyncMock)
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run = mocker.patch("backend.apps.agent_app.agent_run")
    mock_submit = mocker.patch("backend.apps.agent_app.submit")
    
    mock_get_user_info.return_value = ("user_id", "email", "en")
    mock_create_run_info.return_value = mocker.MagicMock()
    
    # Create a real async generator to mock agent_run
    async def mock_async_generator():
        for chunk in ["chunk1", "chunk2"]:
            yield chunk
    
    mock_agent_run.return_value = mock_async_generator()
    
    # Test the endpoint in debug mode
    response = client.post(
        "/agent/run",
        json={
            "agent_id": 123,
            "conversation_id": mock_conversation_id,
            "query": "test query",
            "history": [],
            "minio_files": [],
            "is_debug": True
        },
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_submit.assert_not_called()
    mock_agent_run_manager.unregister_agent_run.assert_called_once_with(mock_conversation_id)


@pytest.mark.asyncio
async def test_agent_run_api_exception(mocker, mock_auth_header, mock_conversation_id):
    # Setup mocks using pytest-mock
    mock_get_user_info = mocker.patch("backend.apps.agent_app.get_current_user_info")
    mock_create_run_info = mocker.patch("backend.apps.agent_app.create_agent_run_info", new_callable=mocker.AsyncMock)
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run = mocker.patch("backend.apps.agent_app.agent_run")
    
    mock_get_user_info.return_value = ("user_id", "email", "en")
    # Make create_agent_run_info throw exception so exception occurs before streaming response starts
    mock_create_run_info.side_effect = Exception("Test error")
    
    # Test the endpoint with exception - use pytest.raises to catch exception
    with pytest.raises(Exception) as exc_info:
        client.post(
            "/agent/run",
            json={
                "agent_id": 123,
                "conversation_id": mock_conversation_id,
                "query": "test query",
                "history": [],
                "minio_files": [],
                "is_debug": False
            },
            headers=mock_auth_header
        )
    
    # Verify exception message
    assert "Test error" in str(exc_info.value)


def test_agent_stop_api_success(mocker, mock_conversation_id):
    # Setup mocks using pytest-mock
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run_manager.stop_agent_run.return_value = True
    
    # Test the endpoint
    response = client.get(f"/agent/stop/{mock_conversation_id}")
    
    # Assertions
    assert response.status_code == 200
    mock_agent_run_manager.stop_agent_run.assert_called_once_with(mock_conversation_id)
    assert "success" in response.json()["status"]


def test_agent_stop_api_not_found(mocker, mock_conversation_id):
    # Setup mocks using pytest-mock
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run_manager.stop_agent_run.return_value = False
    
    # Test the endpoint
    response = client.get(f"/agent/stop/{mock_conversation_id}")
    
    # Assertions
    assert response.status_code == 404
    mock_agent_run_manager.stop_agent_run.assert_called_once_with(mock_conversation_id)
    assert "no running agent found" in response.json()["detail"]


def test_reload_config(mocker):
    # Setup mocks using pytest-mock
    mock_config_manager = mocker.patch("backend.apps.agent_app.config_manager")
    mock_config_manager.force_reload.return_value = {"status": "reloaded"}
    
    # Test the endpoint
    response = client.post("/agent/reload_config")
    
    # Assertions
    assert response.status_code == 200
    mock_config_manager.force_reload.assert_called_once()
    assert response.json() == {"status": "reloaded"}


def test_list_main_agent_info_api_success(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_list_main_agent = mocker.patch("backend.apps.agent_app.list_main_agent_info_impl")
    mock_list_main_agent.return_value = [{"agent_id": "agent1"}, {"agent_id": "agent2"}]
    
    # Test the endpoint
    response = client.get("/agent/list", headers=mock_auth_header)
    
    # Assertions
    assert response.status_code == 200
    mock_list_main_agent.assert_called_once_with(mock_auth_header["Authorization"])
    assert len(response.json()) == 2


def test_list_main_agent_info_api_exception(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_list_main_agent = mocker.patch("backend.apps.agent_app.list_main_agent_info_impl")
    mock_list_main_agent.side_effect = Exception("Test error")
    
    # Test the endpoint
    response = client.get("/agent/list", headers=mock_auth_header)
    
    # Assertions
    assert response.status_code == 500
    assert "Agent list error" in response.json()["detail"]


def test_search_agent_info_api_success(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_get_agent_info = mocker.patch("backend.apps.agent_app.get_agent_info_impl")
    mock_get_agent_info.return_value = {"agent_id": 123, "name": "Test Agent"}
    
    # Test the endpoint
    response = client.post(
        "/agent/search_info",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_get_agent_info.assert_called_once_with(123, mock_auth_header["Authorization"])
    assert response.json()["agent_id"] == 123


def test_search_agent_info_api_exception(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_get_agent_info = mocker.patch("backend.apps.agent_app.get_agent_info_impl")
    mock_get_agent_info.side_effect = Exception("Test error")
    
    # Test the endpoint
    response = client.post(
        "/agent/search_info",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 500
    assert "Agent search info error" in response.json()["detail"]


def test_get_creating_sub_agent_info_api_success(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_get_creating_agent = mocker.patch("backend.apps.agent_app.get_creating_sub_agent_info_impl")
    mock_get_creating_agent.return_value = {"agent_id": 456}
    
    # Test the endpoint
    response = client.post(
        "/agent/get_creating_sub_agent_id",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_get_creating_agent.assert_called_once_with(123, mock_auth_header["Authorization"])
    assert response.json()["agent_id"] == 456


def test_get_creating_sub_agent_info_api_exception(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_get_creating_agent = mocker.patch("backend.apps.agent_app.get_creating_sub_agent_info_impl")
    mock_get_creating_agent.side_effect = Exception("Test error")
    
    # Test the endpoint
    response = client.post(
        "/agent/get_creating_sub_agent_id",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 500
    assert "Agent create error" in response.json()["detail"]


def test_update_agent_info_api_success(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_update_agent = mocker.patch("backend.apps.agent_app.update_agent_info_impl")
    mock_update_agent.return_value = None
    
    # Test the endpoint
    response = client.post(
        "/agent/update",
        json={"agent_id": 123, "name": "Updated Agent"},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_update_agent.assert_called_once()
    assert response.json() == {}


def test_update_agent_info_api_exception(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_update_agent = mocker.patch("backend.apps.agent_app.update_agent_info_impl")
    mock_update_agent.side_effect = Exception("Test error")
    
    # Test the endpoint
    response = client.post(
        "/agent/update",
        json={"agent_id": 123, "name": "Updated Agent"},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 500
    assert "Agent update error" in response.json()["detail"]


def test_delete_agent_api_success(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_delete_agent = mocker.patch("backend.apps.agent_app.delete_agent_impl")
    mock_delete_agent.return_value = None
    
    # Test the endpoint
    response = client.request(
        "DELETE",
        "/agent",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_delete_agent.assert_called_once_with(123, mock_auth_header["Authorization"])
    assert response.json() == {}


def test_delete_agent_api_exception(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_delete_agent = mocker.patch("backend.apps.agent_app.delete_agent_impl")
    mock_delete_agent.side_effect = Exception("Test error")
    
    # Test the endpoint
    response = client.request(
        "DELETE",
        "/agent",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 500
    assert "Agent delete error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_export_agent_api_success(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_export_agent = mocker.patch("backend.apps.agent_app.export_agent_impl")
    mock_export_agent.return_value = '{"agent_id": 123, "name": "Test Agent"}'
    
    # Test the endpoint
    response = client.post(
        "/agent/export",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_export_agent.assert_called_once_with(123, mock_auth_header["Authorization"])
    assert response.json()["code"] == 0
    assert response.json()["message"] == "success"


@pytest.mark.asyncio
async def test_export_agent_api_exception(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_export_agent = mocker.patch("backend.apps.agent_app.export_agent_impl")
    mock_export_agent.side_effect = Exception("Test error")
    
    # Test the endpoint
    response = client.post(
        "/agent/export",
        json={"agent_id": 123},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 500
    assert "Agent export error" in response.json()["detail"]


def test_import_agent_api_success(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_import_agent = mocker.patch("backend.apps.agent_app.import_agent_impl")
    mock_import_agent.return_value = None
    
    # Test the endpoint
    response = client.post(
        "/agent/import",
        json={
            "agent_id": 123,
            "agent_info": {
                "name": "Imported Agent",
                "description": "Test description",
                "business_description": "Test business",
                "model_name": "gpt-4",
                "max_steps": 10,
                "provide_run_summary": True,
                "prompt": "Test prompt",
                "enabled": True,
                "tools": [],
                "managed_agents": []
            }
        },
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_import_agent.assert_called_once()
    args, kwargs = mock_import_agent.call_args
    assert args[0] == 123
    assert args[2] == mock_auth_header["Authorization"]
    assert args[1].name == "Imported Agent"
    assert args[1].description == "Test description"
    assert args[1].business_description == "Test business"
    assert args[1].model_name == "gpt-4"
    assert args[1].max_steps == 10
    assert args[1].provide_run_summary == True
    assert args[1].prompt == "Test prompt"
    assert args[1].enabled == True
    assert args[1].tools == []
    assert args[1].managed_agents == []
    assert response.json() == {}


def test_import_agent_api_exception(mocker, mock_auth_header):
    # Setup mocks using pytest-mock
    mock_import_agent = mocker.patch("backend.apps.agent_app.import_agent_impl")
    mock_import_agent.side_effect = Exception("Test error")
    
    # Test the endpoint
    response = client.post(
        "/agent/import",
        json={
            "agent_id": 123,
            "agent_info": {
                "name": "Imported Agent",
                "description": "Test description",
                "business_description": "Test business",
                "model_name": "gpt-4",
                "max_steps": 10,
                "provide_run_summary": True,
                "prompt": "Test prompt",
                "enabled": True,
                "tools": [],
                "managed_agents": []
            }
        },
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 500
    assert "Agent import error" in response.json()["detail"]


@pytest.mark.asyncio
async def test_agent_run_api_streaming_response(mocker, mock_auth_header):
    """Detailed testing of agent_run_api function's StreamingResponse and async generation part"""
    # Setup mocks using pytest-mock
    mock_get_user_info = mocker.patch("backend.apps.agent_app.get_current_user_info")
    mock_create_run_info = mocker.patch("backend.apps.agent_app.create_agent_run_info", new_callable=mocker.AsyncMock)
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run = mocker.patch("backend.apps.agent_app.agent_run")
    mock_submit = mocker.patch("backend.apps.agent_app.submit")
    
    mock_get_user_info.return_value = ("user_id", "email", "en")
    mock_create_run_info.return_value = mocker.MagicMock()
    
    # Mock async generator returning multiple chunks
    chunks = ["chunk1", "chunk2", "chunk3"]
    async def mock_async_generator():
        for chunk in chunks:
            yield chunk
            
    mock_agent_run.return_value = mock_async_generator()
    
    # Create test client
    test_client = TestClient(app)
    
    # Send request but don't wait for complete response (because we need to manually iterate streaming response)
    with test_client.stream("POST", 
        "/agent/run",
        json={
            "agent_id": 123,
            "conversation_id": 456,
            "query": "test streaming",
            "history": [],
            "minio_files": [],
            "is_debug": False
        },
        headers=mock_auth_header
    ) as response:
        # Verify response status code
        assert response.status_code == 200
        
        # Verify response headers
        assert response.headers["Content-Type"].startswith("text/event-stream")
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        
        # Collect streaming response content
        content = ""
        for line in response.iter_lines():
            if line:
                content += line + "\n"
        
        # Verify content contains all chunks
        for chunk in chunks:
            assert f"data: {chunk}" in content
    
    # Verify non-debug mode behavior
    mock_submit.assert_called()
    mock_agent_run_manager.register_agent_run.assert_called_once()
    mock_agent_run_manager.unregister_agent_run.assert_called_once_with(456)


@pytest.mark.asyncio
async def test_agent_run_api_streaming_exception(mocker, mock_auth_header):
    """Test exception handling and cleanup logic in agent_run_api function"""
    # Setup mocks using pytest-mock
    mock_get_user_info = mocker.patch("backend.apps.agent_app.get_current_user_info")
    mock_create_run_info = mocker.patch("backend.apps.agent_app.create_agent_run_info", new_callable=mocker.AsyncMock)
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run = mocker.patch("backend.apps.agent_app.agent_run")
    mock_submit = mocker.patch("backend.apps.agent_app.submit")
    
    mock_get_user_info.return_value = ("user_id", "email", "en")
    mock_create_run_info.return_value = mocker.MagicMock()
    
    # Create an async generator that throws exception
    async def mock_async_generator_with_exception():
        yield "chunk1"  # First produce a normal chunk
        raise Exception("Stream error")  # Then throw exception
            
    mock_agent_run.return_value = mock_async_generator_with_exception()
    
    # Test streaming response exception handling - exception after streaming starts cannot change HTTP status code
    # We mainly test whether cleanup logic is executed correctly
    test_client = TestClient(app)
    
    # Due to streaming response characteristics, we use pytest.raises to catch underlying exception
    with pytest.raises(RuntimeError, match="Caught handled exception, but response already started"):
        with test_client.stream("POST", 
            "/agent/run",
            json={
                "agent_id": 123,
                "conversation_id": 789,
                "query": "test exception",
                "history": [],
                "minio_files": [],
                "is_debug": False
            },
            headers=mock_auth_header
        ) as response:
            # Trying to read streaming content will trigger exception
            for line in response.iter_lines():
                if line:
                    pass
    
    # Verify cleanup logic is called (this is what we really care about)
    mock_agent_run_manager.unregister_agent_run.assert_called_once_with(789)


@pytest.mark.asyncio
async def test_agent_run_api_chunked_streaming(mocker, mock_auth_header):
    """Detailed testing of agent_run_api function's handling of different sized chunks"""
    # Setup mocks using pytest-mock
    mock_get_user_info = mocker.patch("backend.apps.agent_app.get_current_user_info")
    mock_create_run_info = mocker.patch("backend.apps.agent_app.create_agent_run_info", new_callable=mocker.AsyncMock)
    mock_agent_run_manager = mocker.patch("backend.apps.agent_app.agent_run_manager")
    mock_agent_run = mocker.patch("backend.apps.agent_app.agent_run")
    mock_submit = mocker.patch("backend.apps.agent_app.submit")
    
    mock_get_user_info.return_value = ("user_id", "email", "en")
    mock_create_run_info.return_value = mocker.MagicMock()
    
    # Mock async generator returning different sized chunks
    chunks = ["small", "medium_sized_chunk", "this_is_a_very_large_chunk_to_test_buffer_handling"*5]
    async def mock_async_generator():
        for chunk in chunks:
            yield chunk
            
    mock_agent_run.return_value = mock_async_generator()
    
    # Create test client
    test_client = TestClient(app)
    
    # Send request
    with test_client.stream("POST", 
        "/agent/run",
        json={
            "agent_id": 123,
            "conversation_id": 101,
            "query": "test different chunks",
            "history": [],
            "minio_files": [],
            "is_debug": True  # Use debug mode this time
        },
        headers=mock_auth_header
    ) as response:
        # Verify response status code
        assert response.status_code == 200
        
        # Collect streaming response content
        content = ""
        for line in response.iter_lines():
            if line:
                content += line + "\n"
        
        # Verify content contains all chunks
        for chunk in chunks:
            assert f"data: {chunk}" in content
    
    # Verify debug mode behavior
    mock_submit.assert_not_called()  # Don't save conversation in debug mode
    mock_agent_run_manager.register_agent_run.assert_called_once()
    mock_agent_run_manager.unregister_agent_run.assert_called_once_with(101)


@pytest.mark.asyncio
async def test_export_agent_api_detailed(mocker, mock_auth_header):
    """Detailed testing of export_agent_api function, including ConversationResponse construction"""
    # Setup mocks using pytest-mock
    mock_export_agent = mocker.patch("backend.apps.agent_app.export_agent_impl")
    
    # Setup mocks - return complex JSON data
    agent_data = {
        "agent_id": 456,
        "name": "Complex Agent",
        "description": "Detailed testing",
        "tools": [{"id": 1, "name": "tool1"}, {"id": 2, "name": "tool2"}],
        "managed_agents": [789, 101],
        "other_fields": "some values"
    }
    mock_export_agent.return_value = agent_data
    
    # Test with complex data
    response = client.post(
        "/agent/export",
        json={"agent_id": 456},
        headers=mock_auth_header
    )
    
    # Assertions
    assert response.status_code == 200
    mock_export_agent.assert_called_once_with(456, mock_auth_header["Authorization"])
    
    # Verify correct construction of ConversationResponse
    response_data = response.json()
    assert response_data["code"] == 0
    assert response_data["message"] == "success"
    assert response_data["data"] == agent_data


@pytest.mark.asyncio
async def test_export_agent_api_empty_response(mocker, mock_auth_header):
    """Test export_agent_api handling empty response"""
    # Setup mocks using pytest-mock
    mock_export_agent = mocker.patch("backend.apps.agent_app.export_agent_impl")
    
    # Setup mock to return empty data
    mock_export_agent.return_value = {}
    
    # Send request
    response = client.post(
        "/agent/export",
        json={"agent_id": 789},
        headers=mock_auth_header
    )
    
    # Verify
    assert response.status_code == 200
    mock_export_agent.assert_called_once_with(789, mock_auth_header["Authorization"])
    
    # Verify empty data can also be correctly wrapped in ConversationResponse
    response_data = response.json()
    assert response_data["code"] == 0
    assert response_data["message"] == "success"
    assert response_data["data"] == {}
