import unittest
from unittest.mock import patch, MagicMock, mock_open, ANY
import queue

# Mock boto3 and minio client before importing the module under test
import sys
boto3_mock = MagicMock()
sys.modules['boto3'] = boto3_mock

# Mock ElasticSearch before importing other modules
elasticsearch_mock = MagicMock()
sys.modules['elasticsearch'] = elasticsearch_mock

# Mock MinioClient class before importing the services
minio_client_mock = MagicMock()
with patch('backend.database.client.MinioClient', return_value=minio_client_mock):
    with patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore', return_value=MagicMock()):
        with patch('nexent.vector_database.elasticsearch_core.Elasticsearch', return_value=MagicMock()):
            from jinja2 import StrictUndefined

            from backend.services.prompt_service import (
                call_llm_for_system_prompt,
                generate_and_save_system_prompt_impl,
                get_enabled_tool_description_for_generate_prompt,
                get_enabled_sub_agent_description_for_generate_prompt,
                fine_tune_prompt,
                generate_system_prompt,
                join_info_for_generate_system_prompt
            )
            from backend.consts.model import AgentInfoRequest


class TestPromptService(unittest.TestCase):
    
    def setUp(self):
        # Reset all mocks before each test
        minio_client_mock.reset_mock()

    @patch('backend.services.prompt_service.OpenAIServerModel')
    @patch('backend.services.prompt_service.tenant_config_manager')
    @patch('backend.services.prompt_service.get_model_name_from_config')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_call_llm_for_system_prompt(self, mock_elasticsearch, mock_es_core, mock_get_model_name, mock_tenant_config, mock_openai):
        # Setup
        mock_model_config = {
            "base_url": "http://example.com",
            "api_key": "fake-key"
        }
        mock_tenant_config.get_model_config.return_value = mock_model_config
        mock_get_model_name.return_value = "gpt-4"
        
        mock_llm_instance = mock_openai.return_value
        
        # Mock the streaming response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Generated prompt"
        
        # Set up the client.chat.completions.create mock
        mock_llm_instance.client = MagicMock()
        mock_llm_instance.client.chat.completions.create.return_value = [mock_chunk]
        mock_llm_instance._prepare_completion_kwargs.return_value = {}
        
        # Execute
        result = call_llm_for_system_prompt("user prompt", "system prompt")
        
        # Assert
        self.assertEqual(result, "Generated prompt")
        mock_openai.assert_called_once_with(
            model_id="gpt-4",
            api_base="http://example.com",
            api_key="fake-key",
            temperature=0.3,
            top_p=0.95
        )
        
    @patch('backend.services.prompt_service.generate_system_prompt')
    @patch('backend.services.prompt_service.get_enabled_sub_agent_description_for_generate_prompt')
    @patch('backend.services.prompt_service.get_enabled_tool_description_for_generate_prompt')
    @patch('backend.services.prompt_service.get_current_user_info')
    @patch('backend.services.prompt_service.update_agent')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_generate_and_save_system_prompt_impl(self, mock_elasticsearch, mock_es_core, mock_update_agent, mock_get_user_info, 
                                         mock_get_tool_desc, mock_get_agent_desc, 
                                         mock_generate_system_prompt):
        # Setup
        mock_get_user_info.return_value = ("user123", "tenant456", "zh")
        
        mock_tool1 = {"name": "tool1", "description": "Tool 1 desc", "inputs": "input1", "output_type": "output1"}
        mock_tool2 = {"name": "tool2", "description": "Tool 2 desc", "inputs": "input2", "output_type": "output2"}
        mock_get_tool_desc.return_value = [mock_tool1, mock_tool2]
        
        mock_agent1 = {"name": "agent1", "description": "Agent 1 desc", "enabled": True}
        mock_agent2 = {"name": "agent2", "description": "Agent 2 desc", "enabled": True}
        mock_get_agent_desc.return_value = [mock_agent1, mock_agent2]
        
        # Mock the generator to return the expected data structure
        def mock_generator(*args, **kwargs):
            yield {"type": "duty", "content": "Generated duty prompt", "is_complete": False}
            yield {"type": "constraint", "content": "Generated constraint prompt", "is_complete": False}
            yield {"type": "few_shots", "content": "Generated few shots prompt", "is_complete": False}
            yield {"type": "duty", "content": "Final duty prompt", "is_complete": True}
            yield {"type": "constraint", "content": "Final constraint prompt", "is_complete": True}
            yield {"type": "few_shots", "content": "Final few shots prompt", "is_complete": True}
        
        mock_generate_system_prompt.side_effect = mock_generator
        
        # Execute - test as a generator
        result_gen = generate_and_save_system_prompt_impl(123, "Test task", "fake-auth-token")
        result = list(result_gen)  # Convert generator to list for assertion
        
        # Assert
        expected_results = [
            {"type": "duty", "content": "Generated duty prompt", "is_complete": False},
            {"type": "constraint", "content": "Generated constraint prompt", "is_complete": False},
            {"type": "few_shots", "content": "Generated few shots prompt", "is_complete": False},
            {"type": "duty", "content": "Final duty prompt", "is_complete": True},
            {"type": "constraint", "content": "Final constraint prompt", "is_complete": True},
            {"type": "few_shots", "content": "Final few shots prompt", "is_complete": True}
        ]
        self.assertEqual(result, expected_results)
        
        mock_get_user_info.assert_called_once_with("fake-auth-token", None)
        mock_get_tool_desc.assert_called_once_with(agent_id=123, tenant_id="tenant456", user_id="user123")
        mock_get_agent_desc.assert_called_once_with(agent_id=123, tenant_id="tenant456", user_id="user123")
        
        mock_generate_system_prompt.assert_called_once_with(
            mock_get_agent_desc.return_value,
            "Test task",
            mock_get_tool_desc.return_value,
            "tenant456",
            "zh"
        )
        
        # Verify update_agent was called with the correct parameters
        mock_update_agent.assert_called_once()
        call_args = mock_update_agent.call_args
        self.assertEqual(call_args[1]['agent_id'], 123)
        self.assertEqual(call_args[1]['tenant_id'], "tenant456")
        self.assertEqual(call_args[1]['user_id'], "user123")
        
        # Verify the agent_info object has the correct structure
        agent_info = call_args[1]['agent_info']
        self.assertEqual(agent_info.agent_id, 123)
        self.assertEqual(agent_info.business_description, "Test task")
        self.assertEqual(agent_info.duty_prompt, "Final duty prompt")
        self.assertEqual(agent_info.constraint_prompt, "Final constraint prompt")
        self.assertEqual(agent_info.few_shots_prompt, "Final few shots prompt")

    @patch('backend.services.prompt_service.call_llm_for_system_prompt')
    @patch('backend.services.prompt_service.join_info_for_generate_system_prompt')
    @patch('backend.services.prompt_service.get_prompt_generate_prompt_template')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_generate_system_prompt(self, mock_elasticsearch, mock_es_core, mock_get_prompt_template, 
                                   mock_join_info, mock_call_llm):
        # Setup
        mock_prompt_config = {
            "USER_PROMPT": "Test user prompt template",
            "DUTY_SYSTEM_PROMPT": "Generate duty prompt",
            "CONSTRAINT_SYSTEM_PROMPT": "Generate constraint prompt", 
            "FEW_SHOTS_SYSTEM_PROMPT": "Generate few shots prompt",
            "AGENT_VARIABLE_NAME_SYSTEM_PROMPT": "Generate agent var name",
            "AGENT_DISPLAY_NAME_SYSTEM_PROMPT": "Generate agent display name",
            "AGENT_DESCRIPTION_SYSTEM_PROMPT": "Generate agent description"
        }
        mock_get_prompt_template.return_value = mock_prompt_config
        
        mock_join_info.return_value = "Joined template content"
        
        # Mock call_llm_for_system_prompt to simulate streaming responses
        def mock_llm_call(content, sys_prompt, callback, tenant_id):
            # Simulate different responses based on system prompt
            if "duty" in sys_prompt.lower():
                if callback:
                    callback("Duty prompt part 1")
                    callback("Duty prompt part 1 part 2")
                return "Duty prompt part 1 part 2"
            elif "constraint" in sys_prompt.lower():
                if callback:
                    callback("Constraint prompt part 1")
                    callback("Constraint prompt part 1 part 2")
                return "Constraint prompt part 1 part 2"
            elif "few_shots" in sys_prompt.lower():
                if callback:
                    callback("Few shots prompt part 1")
                    callback("Few shots prompt part 1 part 2")
                return "Few shots prompt part 1 part 2"
            elif "variable_name" in sys_prompt.lower():
                if callback:
                    callback("test_agent")
                return "test_agent"
            elif "display_name" in sys_prompt.lower():
                if callback:
                    callback("Test Agent")
                return "Test Agent"
            elif "description" in sys_prompt.lower():
                if callback:
                    callback("Test agent description")
                return "Test agent description"
            return "Default response"
        
        mock_call_llm.side_effect = mock_llm_call
        
        # Test data
        mock_sub_agents = [{"name": "agent1", "description": "Agent 1"}]
        mock_task_description = "Test task"
        mock_tools = [{"name": "tool1", "description": "Tool 1"}]
        mock_tenant_id = "test_tenant"
        mock_language = "zh"
        
        # Execute - collect all results from the generator
        from backend.services.prompt_service import generate_system_prompt
        result_list = []
        for result in generate_system_prompt(
            mock_sub_agents,
            mock_task_description,
            mock_tools,
            mock_tenant_id,
            mock_language
        ):
            result_list.append(result)
        
        # Assert
        # Verify template loading
        mock_get_prompt_template.assert_called_once_with(mock_language)
        
        # Verify template joining
        mock_join_info.assert_called_once_with(
            mock_prompt_config,
            mock_sub_agents,
            mock_task_description,
            mock_tools
        )
        
        # Verify LLM calls - should be called 6 times for each prompt type
        self.assertEqual(mock_call_llm.call_count, 6)
        
        # Verify that results contain the expected structure
        # Should have streaming results and final results
        self.assertTrue(len(result_list) > 0)
        
        # Check that we get results for all expected types
        result_types = [r["type"] for r in result_list]
        expected_types = ["duty", "constraint", "few_shots", "agent_var_name", "agent_display_name", "agent_description"]
        
        for expected_type in expected_types:
            self.assertIn(expected_type, result_types, f"Missing result type: {expected_type}")
        
        # Check that all final results are marked as complete
        final_results = [r for r in result_list if r.get("is_complete", False)]
        final_types = [r["type"] for r in final_results]
        
        for expected_type in expected_types:
            self.assertIn(expected_type, final_types, f"Missing final result for type: {expected_type}")
        
        # Verify content structure
        for result in result_list:
            self.assertIn("type", result)
            self.assertIn("content", result)
            self.assertIn("is_complete", result)
            self.assertIsInstance(result["is_complete"], bool)
            self.assertIsInstance(result["content"], str)

    @patch('backend.services.prompt_service.call_llm_for_system_prompt')
    @patch('backend.services.prompt_service.join_info_for_generate_system_prompt')
    @patch('backend.services.prompt_service.get_prompt_generate_prompt_template')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_generate_system_prompt_with_exception(self, mock_elasticsearch, mock_es_core, mock_get_prompt_template,
                                                  mock_join_info, mock_call_llm):
        # Setup
        mock_prompt_config = {
            "USER_PROMPT": "Test user prompt template",
            "DUTY_SYSTEM_PROMPT": "Generate duty prompt",
            "CONSTRAINT_SYSTEM_PROMPT": "Generate constraint prompt",
            "FEW_SHOTS_SYSTEM_PROMPT": "Generate few shots prompt",
            "AGENT_VARIABLE_NAME_SYSTEM_PROMPT": "Generate agent var name",
            "AGENT_DISPLAY_NAME_SYSTEM_PROMPT": "Generate agent display name",
            "AGENT_DESCRIPTION_SYSTEM_PROMPT": "Generate agent description"
        }
        mock_get_prompt_template.return_value = mock_prompt_config
        mock_join_info.return_value = "Joined template content"
        
        # Mock call_llm_for_system_prompt to raise exception for one prompt type
        def mock_llm_call_with_exception(content, sys_prompt, callback, tenant_id):
            if "duty" in sys_prompt.lower():
                raise Exception("LLM error for duty prompt")
            elif "constraint" in sys_prompt.lower():
                if callback:
                    callback("Constraint prompt")
                return "Constraint prompt"
            else:
                if callback:
                    callback("Other prompt")
                return "Other prompt"
        
        mock_call_llm.side_effect = mock_llm_call_with_exception
        
        # Test data
        mock_sub_agents = [{"name": "agent1", "description": "Agent 1"}]
        mock_task_description = "Test task"
        mock_tools = [{"name": "tool1", "description": "Tool 1"}]
        mock_tenant_id = "test_tenant"
        mock_language = "en"
        
        # Execute - should handle exceptions gracefully
        from backend.services.prompt_service import generate_system_prompt
        result_list = []
        for result in generate_system_prompt(
            mock_sub_agents,
            mock_task_description,
            mock_tools,
            mock_tenant_id,
            mock_language
        ):
            result_list.append(result)
        
        # Assert - should still return results for other prompt types
        self.assertTrue(len(result_list) > 0)
        
        # Should have results for constraint and other types, but duty might be empty due to exception
        result_types = [r["type"] for r in result_list]
        
        # Constraint should work fine
        constraint_results = [r for r in result_list if r["type"] == "constraint"]
        self.assertTrue(len(constraint_results) > 0)
        
        # Verify that duty result exists but might be empty due to exception handling
        duty_results = [r for r in result_list if r["type"] == "duty"]
        self.assertTrue(len(duty_results) > 0)  # Should still have duty result entry with empty content

    @patch('backend.services.prompt_service.Template')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_join_info_for_generate_system_prompt(self, mock_elasticsearch, mock_es_core, mock_template):
        # Setup
        mock_prompt_for_generate = {"USER_PROMPT": "Test User Prompt"}
        mock_sub_agents = [
            {"name": "agent1", "description": "Agent 1 desc"},
            {"name": "agent2", "description": "Agent 2 desc"}
        ]
        mock_task_description = "Test task"
        mock_tools = [
            {"name": "tool1", "description": "Tool 1 desc", "inputs": "input1", "output_type": "output1"},
            {"name": "tool2", "description": "Tool 2 desc", "inputs": "input2", "output_type": "output2"}
        ]
        
        mock_template_instance = MagicMock()
        mock_template.return_value = mock_template_instance
        mock_template_instance.render.return_value = "Rendered content"
        
        # Execute
        result = join_info_for_generate_system_prompt(
            mock_prompt_for_generate, mock_sub_agents, mock_task_description, mock_tools
        )
        
        # Assert
        self.assertEqual(result, "Rendered content")
        mock_template.assert_called_once_with(mock_prompt_for_generate["USER_PROMPT"], undefined=StrictUndefined)
        mock_template_instance.render.assert_called_once()
        # Check template variables
        template_vars = mock_template_instance.render.call_args[0][0]
        self.assertTrue("tool_description" in template_vars)
        self.assertTrue("agent_description" in template_vars)
        self.assertEqual(template_vars["task_description"], mock_task_description)
        
    @patch('backend.services.prompt_service.get_enable_tool_id_by_agent_id')
    @patch('backend.services.prompt_service.query_tools_by_ids')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_get_enabled_tool_description_for_generate_prompt(self, mock_elasticsearch, mock_es_core, mock_query_tools, mock_get_tool_ids):
        # Setup
        mock_get_tool_ids.return_value = [1, 2, 3]
        mock_tools = [{"id": 1, "name": "tool1"}, {"id": 2, "name": "tool2"}, {"id": 3, "name": "tool3"}]
        mock_query_tools.return_value = mock_tools
        
        # Execute
        result = get_enabled_tool_description_for_generate_prompt(
            agent_id=123, 
            tenant_id="tenant456", 
            user_id="user123"
        )
        
        # Assert
        self.assertEqual(result, mock_tools)
        mock_get_tool_ids.assert_called_once_with(agent_id=123, tenant_id="tenant456", user_id="user123")
        mock_query_tools.assert_called_once_with([1, 2, 3])
        
    @patch('backend.services.prompt_service.search_agent_info_by_agent_id')
    @patch('backend.services.prompt_service.query_sub_agents_id_list')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_get_enabled_sub_agent_description_for_generate_prompt(self, mock_elasticsearch, mock_es_core, mock_query_sub_agents_id_list, mock_search_agent_info):
        # Setup
        mock_query_sub_agents_id_list.return_value = [1, 2, 3]
        
        # Mock search_agent_info_by_agent_id to return different agent info for each ID
        def mock_search_agent_info_side_effect(agent_id, tenant_id):
            agent_info_map = {
                1: {"id": 1, "name": "agent1", "enabled": True},
                2: {"id": 2, "name": "agent2", "enabled": False},
                3: {"id": 3, "name": "agent3", "enabled": True}
            }
            return agent_info_map.get(agent_id, {})
        
        mock_search_agent_info.side_effect = mock_search_agent_info_side_effect
        
        # Execute
        result = get_enabled_sub_agent_description_for_generate_prompt(
            agent_id=123, 
            tenant_id="tenant456", 
            user_id="user123"
        )
        
        # Assert
        expected_result = [
            {"id": 1, "name": "agent1", "enabled": True},
            {"id": 2, "name": "agent2", "enabled": False},
            {"id": 3, "name": "agent3", "enabled": True}
        ]
        self.assertEqual(result, expected_result)
        mock_query_sub_agents_id_list.assert_called_once_with(main_agent_id=123, tenant_id="tenant456")
        
        # Verify search_agent_info_by_agent_id was called for each sub agent ID
        self.assertEqual(mock_search_agent_info.call_count, 3)
        mock_search_agent_info.assert_any_call(agent_id=1, tenant_id="tenant456")
        mock_search_agent_info.assert_any_call(agent_id=2, tenant_id="tenant456")
        mock_search_agent_info.assert_any_call(agent_id=3, tenant_id="tenant456")
        
    @patch('backend.services.prompt_service.call_llm_for_system_prompt')
    @patch('backend.services.prompt_service.open', new_callable=mock_open, read_data="""
FINE_TUNE_USER_PROMPT: "Test Fine Tune User Prompt {{prompt}} {{command}}"
FINE_TUNE_SYSTEM_PROMPT: "Fine Tune System Prompt"
""")
    @patch('backend.services.prompt_service.yaml.safe_load')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_fine_tune_prompt(self, mock_elasticsearch, mock_es_core, mock_yaml_load, mock_open_file, mock_call_llm):
        # Setup
        mock_yaml_data = {
            "FINE_TUNE_USER_PROMPT": "Test Fine Tune User Prompt {{prompt}} {{command}}",
            "FINE_TUNE_SYSTEM_PROMPT": "Fine Tune System Prompt"
        }
        mock_yaml_load.return_value = mock_yaml_data
        mock_call_llm.return_value = "Fine-tuned prompt result"
        
        # Execute
        result = fine_tune_prompt("Original prompt", "Command", tenant_id="test_tenant")
        
        # Assert
        self.assertEqual(result, "Fine-tuned prompt result")
        mock_call_llm.assert_called_once_with(
            user_prompt=ANY,  # Using ANY because the Template.render() result is complex to reproduce
            system_prompt="Fine Tune System Prompt",
            tenant_id="test_tenant"
        )
        
    @patch('backend.services.prompt_service.OpenAIServerModel')
    @patch('backend.services.prompt_service.tenant_config_manager')
    @patch('backend.services.prompt_service.get_model_name_from_config')
    @patch('nexent.vector_database.elasticsearch_core.ElasticSearchCore')
    @patch('elasticsearch.Elasticsearch')
    def test_call_llm_for_system_prompt_exception(self, mock_elasticsearch, mock_es_core, mock_get_model_name, mock_tenant_config, mock_openai):
        # Setup
        mock_model_config = {
            "base_url": "http://example.com",
            "api_key": "fake-key"
        }
        mock_tenant_config.get_model_config.return_value = mock_model_config
        mock_get_model_name.return_value = "gpt-4"
        
        mock_llm_instance = mock_openai.return_value
        mock_llm_instance.client = MagicMock()
        mock_llm_instance.client.chat.completions.create.side_effect = Exception("LLM error")
        mock_llm_instance._prepare_completion_kwargs.return_value = {}
        
        # Execute and Assert
        with self.assertRaises(Exception) as context:
            call_llm_for_system_prompt("user prompt", "system prompt")
            
        self.assertTrue("LLM error" in str(context.exception))


if __name__ == '__main__':
    unittest.main()
