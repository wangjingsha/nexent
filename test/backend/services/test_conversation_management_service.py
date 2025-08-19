import unittest
import json
from datetime import datetime
from unittest.mock import patch, MagicMock, mock_open

# Mock boto3 and minio client before importing the module under test
import sys
boto3_mock = MagicMock()
sys.modules['boto3'] = boto3_mock

# Mock MinioClient class before importing the services
minio_client_mock = MagicMock()
with patch('backend.database.client.MinioClient', return_value=minio_client_mock):
    from backend.services.conversation_management_service import (
        save_message,
        save_conversation_user,
        save_conversation_assistant,
        extract_user_messages,
        call_llm_for_title,
        update_conversation_title,
        create_new_conversation,
        get_conversation_list_service,
        rename_conversation_service,
        delete_conversation_service,
        get_conversation_history_service,
        get_sources_service,
        generate_conversation_title_service,
        update_message_opinion_service
    )
from backend.consts.model import MessageRequest, AgentRequest, MessageUnit


class TestConversationManagementService(unittest.TestCase):
    def setUp(self):
        """
        Set up test data and reset all mocks before each test.
        """
        self.tenant_id = "test_tenant_id"
        self.user_id = "test_user_id"
        
        # Reset all mocks before each test
        minio_client_mock.reset_mock()

    @patch('backend.services.conversation_management_service.create_conversation_message')
    @patch('backend.services.conversation_management_service.create_source_search')
    @patch('backend.services.conversation_management_service.create_source_image')
    @patch('backend.services.conversation_management_service.create_message_units')
    def test_save_message_with_string_content(self, mock_create_message_units, mock_create_source_image,
                                             mock_create_source_search, mock_create_conversation_message):
        # Setup
        mock_create_conversation_message.return_value = 123  # message_id

        # Create message request with string content
        message_request = MessageRequest(
            conversation_id=456,
            message_idx=1,
            role="user",
            message=[MessageUnit(type="string", content="Hello, this is a test message")],
            minio_files=[]
        )

        # Execute
        result = save_message(message_request)

        # Assert
        self.assertEqual(result.code, 0)
        self.assertEqual(result.message, "success")
        self.assertTrue(result.data)

        # Check if create_conversation_message was called with correct params
        mock_create_conversation_message.assert_called_once()
        call_args = mock_create_conversation_message.call_args[0][0]
        self.assertEqual(call_args['conversation_id'], 456)
        self.assertEqual(call_args['message_idx'], 1)
        self.assertEqual(call_args['role'], "user")
        self.assertEqual(call_args['content'], "Hello, this is a test message")

        # Check that other methods were not called
        mock_create_message_units.assert_not_called()
        mock_create_source_image.assert_not_called()
        mock_create_source_search.assert_not_called()

    @patch('backend.services.conversation_management_service.create_conversation_message')
    @patch('backend.services.conversation_management_service.create_source_search')
    @patch('backend.services.conversation_management_service.create_message_units')
    def test_save_message_with_search_content(self, mock_create_message_units, mock_create_source_search,
                                             mock_create_conversation_message):
        # Setup
        mock_create_conversation_message.return_value = 123  # message_id

        # Create message with search content
        search_content = json.dumps([{
            "source_type": "web",
            "title": "Test Result",
            "url": "https://example.com",
            "text": "Example search result",
            "score": "0.95",
            "score_details": {"accuracy": "0.9", "semantic": "0.8"},
            "published_date": "2023-01-15",
            "cite_index": 1,
            "search_type": "web_search",
            "tool_sign": "web_search"
        }])

        message_request = MessageRequest(
            conversation_id=456,
            message_idx=2,
            role="assistant",
            message=[
                MessageUnit(type="string", content="Here are the search results"),
                MessageUnit(type="search_content", content=search_content)
            ],
            minio_files=[]
        )

        # Execute
        result = save_message(message_request)

        # Assert
        self.assertEqual(result.code, 0)
        self.assertTrue(result.data)

        # Check correct message was created
        mock_create_conversation_message.assert_called_once()
        call_args = mock_create_conversation_message.call_args[0][0]
        self.assertEqual(call_args['content'], "Here are the search results")

        # Check search content was saved
        mock_create_source_search.assert_called_once()
        search_data = mock_create_source_search.call_args[0][0]
        self.assertEqual(search_data['message_id'], 123)
        self.assertEqual(search_data['conversation_id'], 456)
        self.assertEqual(search_data['source_type'], "web")
        self.assertEqual(search_data['score_overall'], 0.95)

        # Check message units were created with placeholder
        mock_create_message_units.assert_called_once()
        units = mock_create_message_units.call_args[0][0]
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0]['type'], 'search_content_placeholder')

    @patch('backend.services.conversation_management_service.save_message')
    def test_save_conversation_user(self, mock_save_message):
        # Setup
        agent_request = AgentRequest(
            conversation_id=123,
            query="What is machine learning?",
            minio_files=[],
            history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"}
            ]
        )

        # Execute
        save_conversation_user(agent_request)

        # Assert
        mock_save_message.assert_called_once()
        request_arg = mock_save_message.call_args[0][0]
        self.assertEqual(request_arg.conversation_id, 123)
        self.assertEqual(request_arg.message_idx, 2)  # Based on 1 user message in history
        self.assertEqual(request_arg.role, "user")
        self.assertEqual(request_arg.message[0].type, "string")
        self.assertEqual(request_arg.message[0].content, "What is machine learning?")

    @patch('backend.services.conversation_management_service.save_message')
    def test_save_conversation_assistant(self, mock_save_message):
        # Setup
        agent_request = AgentRequest(
            conversation_id=123,
            query="What is machine learning?",
            minio_files=[],
            history=[
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"}
            ]
        )

        messages = [
            json.dumps({"type": "model_output_thinking", "content": "Machine learning is "}),
            json.dumps({"type": "model_output_thinking", "content": "a field of AI"})
        ]

        # Execute
        save_conversation_assistant(agent_request, messages)

        # Assert
        mock_save_message.assert_called_once()
        request_arg = mock_save_message.call_args[0][0]
        self.assertEqual(request_arg.conversation_id, 123)
        self.assertEqual(request_arg.message_idx, 3)  # Based on 1 user message in history + current
        self.assertEqual(request_arg.role, "assistant")
        # Check that consecutive model_output_thinking messages were merged
        self.assertEqual(len(request_arg.message), 1)
        self.assertEqual(request_arg.message[0].type, "model_output_thinking")
        self.assertEqual(request_arg.message[0].content, "Machine learning is a field of AI")

    def test_extract_user_messages(self):
        # Setup
        history = [
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI stands for Artificial Intelligence."},
            {"role": "user", "content": "Give me examples of AI applications"}
        ]

        # Execute
        result = extract_user_messages(history)

        # Assert
        self.assertIn("What is AI?", result)
        self.assertIn("Give me examples of AI applications", result)
        self.assertIn("AI stands for Artificial Intelligence.", result)

    @patch('backend.services.conversation_management_service.OpenAIServerModel')
    @patch('backend.services.conversation_management_service.open', new_callable=mock_open, read_data="""
SYSTEM_PROMPT: "Generate a short title"
USER_PROMPT: "Generate a title for: {{content}}"
""")
    @patch('backend.services.conversation_management_service.yaml.safe_load')
    @patch('os.getenv')
    @patch('backend.services.conversation_management_service.tenant_config_manager.get_model_config')
    def test_call_llm_for_title(self, mock_get_model_config, mock_getenv, mock_yaml_load, mock_open_file, mock_openai):
        # Setup
        mock_get_model_config.return_value = {
            "model_name": "gpt-4",
            "model_repo": "openai",
            "base_url": "http://example.com",
            "api_key": "fake-key"
        }

        mock_getenv.side_effect = lambda key: {
            'LLM_MODEL_NAME': 'gpt-4',
            'LLM_MODEL_URL': 'http://example.com',
            'LLM_API_KEY': 'fake-key'
        }.get(key)

        mock_yaml_data = {
            "SYSTEM_PROMPT": "Generate a short title",
            "USER_PROMPT": "Generate a title for: {{content}}"
        }
        mock_yaml_load.return_value = mock_yaml_data

        mock_llm_instance = mock_openai.return_value
        mock_response = MagicMock()
        mock_response.content = "AI Discussion"
        mock_llm_instance.return_value = mock_response

        # Execute
        result = call_llm_for_title("What is AI? AI stands for Artificial Intelligence.", tenant_id=self.tenant_id)

        # Assert
        self.assertEqual(result, "AI Discussion")
        mock_openai.assert_called_once()
        mock_llm_instance.assert_called_once()

    @patch('backend.services.conversation_management_service.rename_conversation')
    def test_update_conversation_title(self, mock_rename_conversation):
        # Setup
        mock_rename_conversation.return_value = True

        # Execute
        result = update_conversation_title(123, "New Title", self.user_id)

        # Assert
        self.assertTrue(result)
        mock_rename_conversation.assert_called_once_with(123, "New Title", self.user_id)

    @patch('backend.services.conversation_management_service.create_conversation')
    def test_create_new_conversation(self, mock_create_conversation):
        # Setup
        mock_create_conversation.return_value = {"conversation_id": 123, "title": "New Chat", "create_time": "2023-04-01"}

        # Execute
        result = create_new_conversation("New Chat", self.user_id)

        # Assert
        self.assertEqual(result["conversation_id"], 123)
        self.assertEqual(result["title"], "New Chat")
        mock_create_conversation.assert_called_once_with("New Chat", self.user_id)

    @patch('backend.services.conversation_management_service.get_conversation_list')
    def test_get_conversation_list_service(self, mock_get_conversation_list):
        # Setup
        mock_conversations = [
            {"conversation_id": 1, "title": "Chat 1", "create_time": "2023-04-01"},
            {"conversation_id": 2, "title": "Chat 2", "create_time": "2023-04-02"}
        ]
        mock_get_conversation_list.return_value = mock_conversations

        # Execute
        result = get_conversation_list_service(self.user_id)

        # Assert
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["conversation_id"], 1)
        self.assertEqual(result[1]["title"], "Chat 2")
        mock_get_conversation_list.assert_called_once_with(self.user_id)

    @patch('backend.services.conversation_management_service.rename_conversation')
    def test_rename_conversation_service(self, mock_rename_conversation):
        # Setup
        mock_rename_conversation.return_value = True

        # Execute
        result = rename_conversation_service(123, "Updated Title", self.user_id)

        # Assert
        self.assertTrue(result)
        mock_rename_conversation.assert_called_once_with(123, "Updated Title", self.user_id)

    @patch('backend.services.conversation_management_service.delete_conversation')
    def test_delete_conversation_service(self, mock_delete_conversation):
        # Setup
        mock_delete_conversation.return_value = True

        # Execute
        result = delete_conversation_service(123, self.user_id)

        # Assert
        self.assertTrue(result)
        mock_delete_conversation.assert_called_once_with(123, self.user_id)

    @patch('backend.services.conversation_management_service.get_conversation_history')
    def test_get_conversation_history_service(self, mock_get_conversation_history):
        # Setup
        mock_history = {
            "conversation_id": 123,
            "create_time": "2023-04-01",
            "message_records": [
                {
                    "message_id": 1,
                    "role": "user",
                    "message_content": "What is AI?",
                    "minio_files": [],
                    "units": []
                },
                {
                    "message_id": 2,
                    "role": "assistant",
                    "message_content": "AI stands for Artificial Intelligence.",
                    "units": [],
                    "opinion_flag": None
                }
            ],
            "search_records": [],
            "image_records": []
        }
        mock_get_conversation_history.return_value = mock_history

        # Execute
        result = get_conversation_history_service(123, self.user_id)

        # Assert
        self.assertEqual(len(result), 1)  # Result is wrapped in a list
        self.assertEqual(result[0]["conversation_id"], "123")  # Converted to string
        self.assertEqual(len(result[0]["message"]), 2)
        # Check message structure
        user_message = result[0]["message"][0]
        self.assertEqual(user_message["role"], "user")
        self.assertEqual(user_message["message"], "What is AI?")

        assistant_message = result[0]["message"][1]
        self.assertEqual(assistant_message["role"], "assistant")
        self.assertEqual(len(assistant_message["message"]), 1)  # Contains final_answer unit
        self.assertEqual(assistant_message["message"][0]["type"], "final_answer")
        self.assertEqual(assistant_message["message"][0]["content"], "AI stands for Artificial Intelligence.")

    @patch('backend.services.conversation_management_service.get_conversation')
    @patch('backend.services.conversation_management_service.get_source_searches_by_message')
    @patch('backend.services.conversation_management_service.get_source_images_by_message')
    def test_get_sources_service_by_message(self, mock_get_images, mock_get_searches, mock_get_conversation):
        # Setup
        mock_get_conversation.return_value = {"conversation_id": 123, "title": "Test Chat"}

        mock_searches = [
            {
                "message_id": 2,
                "source_title": "AI Definition",
                "source_content": "AI stands for Artificial Intelligence",
                "source_type": "web",
                "source_location": "https://example.com/ai",
                "published_date": datetime(2023, 1, 15),
                "score_overall": 0.95,
                "score_accuracy": 0.9,
                "score_semantic": 0.8,
                "cite_index": 1,
                "search_type": "web_search",
                "tool_sign": "web_search"
            }
        ]
        mock_get_searches.return_value = mock_searches

        mock_images = [
            {"message_id": 2, "image_url": "https://example.com/image.jpg"}
        ]
        mock_get_images.return_value = mock_images

        # Execute
        result = get_sources_service(None, 2, user_id=self.user_id)

        # Assert
        self.assertEqual(result["code"], 0)
        self.assertEqual(result["message"], "success")
        # Check searches
        self.assertEqual(len(result["data"]["searches"]), 1)
        search = result["data"]["searches"][0]
        self.assertEqual(search["title"], "AI Definition")
        self.assertEqual(search["url"], "https://example.com/ai")
        self.assertEqual(search["published_date"], "2023-01-15")
        self.assertEqual(search["score"], 0.95)
        self.assertEqual(search["score_details"]["accuracy"], 0.9)
        # Check images
        self.assertEqual(len(result["data"]["images"]), 1)
        self.assertEqual(result["data"]["images"][0], "https://example.com/image.jpg")

    @patch('backend.services.conversation_management_service.extract_user_messages')
    @patch('backend.services.conversation_management_service.call_llm_for_title')
    @patch('backend.services.conversation_management_service.update_conversation_title')
    @patch('backend.services.conversation_management_service.tenant_config_manager.get_model_config')
    def test_generate_conversation_title_service(self, mock_get_model_config, mock_update_title, mock_call_llm, mock_extract_messages):
        # Setup
        mock_get_model_config.return_value = {
            "model_name": "gpt-4",
            "model_repo": "openai",
            "base_url": "http://example.com",
            "api_key": "fake-key"
        }

        mock_extract_messages.return_value = "What is AI? AI stands for Artificial Intelligence."
        mock_call_llm.return_value = "AI Discussion"
        mock_update_title.return_value = True

        history = [
            {"role": "user", "content": "What is AI?"},
            {"role": "assistant", "content": "AI stands for Artificial Intelligence."}
        ]

        # Execute
        import asyncio
        result = asyncio.run(generate_conversation_title_service(123, history, self.user_id, self.tenant_id, "en"))

        # Assert
        self.assertEqual(result, "AI Discussion")
        mock_extract_messages.assert_called_once_with(history)
        mock_call_llm.assert_called_once()
        mock_update_title.assert_called_once_with(123, "AI Discussion", self.user_id)

    @patch('backend.services.conversation_management_service.update_message_opinion')
    def test_update_message_opinion_service(self, mock_update_opinion):
        # Setup
        mock_update_opinion.return_value = True

        # Execute
        result = update_message_opinion_service(123, "Y")

        # Assert
        self.assertTrue(result)
        mock_update_opinion.assert_called_once_with(123, "Y")


if __name__ == '__main__':
    unittest.main()