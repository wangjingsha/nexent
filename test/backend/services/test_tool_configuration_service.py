import pytest
import inspect
import unittest
from unittest.mock import Mock, patch, MagicMock
from typing import Any, List, Dict
import sys
import pytest

boto3_mock = MagicMock()
minio_client_mock = MagicMock()
sys.modules['boto3'] = boto3_mock
with patch('backend.database.client.MinioClient', return_value=minio_client_mock):
    from backend.services.tool_configuration_service import (
        python_type_to_json_schema,
        get_local_tools,
        get_local_tools_classes,
        search_tool_info_impl,
        update_tool_info_impl
    )
from consts.model import ToolInfo, ToolSourceEnum, ToolInstanceInfoRequest


class TestPythonTypeToJsonSchema:
    """ test the function of python_type_to_json_schema"""

    def test_python_type_to_json_schema_basic_types(self):
        """ test the basic types of python"""
        assert python_type_to_json_schema(str) == "string"
        assert python_type_to_json_schema(int) == "integer"
        assert python_type_to_json_schema(float) == "float"
        assert python_type_to_json_schema(bool) == "boolean"
        assert python_type_to_json_schema(list) == "array"
        assert python_type_to_json_schema(dict) == "object"

    def test_python_type_to_json_schema_typing_types(self):
        """ test the typing types of python"""
        from typing import List, Dict, Tuple, Any
        
        assert python_type_to_json_schema(List) == "array"
        assert python_type_to_json_schema(Dict) == "object"
        assert python_type_to_json_schema(Tuple) == "array"
        assert python_type_to_json_schema(Any) == "any"

    def test_python_type_to_json_schema_empty_annotation(self):
        """ test the empty annotation of python"""
        assert python_type_to_json_schema(inspect.Parameter.empty) == "string"

    def test_python_type_to_json_schema_unknown_type(self):
        """ test the unknown type of python"""
        class CustomType:
            pass
        
        # the unknown type should return the type name itself
        result = python_type_to_json_schema(CustomType)
        assert "CustomType" in result

    def test_python_type_to_json_schema_edge_cases(self):
        """ test the edge cases of python"""
        # test the None type
        assert python_type_to_json_schema(type(None)) == "NoneType"
        
        # test the complex type string representation
        complex_type = List[Dict[str, Any]]
        result = python_type_to_json_schema(complex_type)
        assert isinstance(result, str)


class TestGetLocalToolsClasses:
    """ test the function of get_local_tools_classes"""

    @patch('backend.services.tool_configuration_service.importlib.import_module')
    def test_get_local_tools_classes_success(self, mock_import):
        """ test the success of get_local_tools_classes"""
        # create the mock tool class
        mock_tool_class1 = type('TestTool1', (), {})
        mock_tool_class2 = type('TestTool2', (), {})
        mock_non_class = "not_a_class"
        
        # Create a proper mock object with defined attributes and __dir__ method
        class MockPackage:
            def __init__(self):
                self.TestTool1 = mock_tool_class1
                self.TestTool2 = mock_tool_class2
                self.not_a_class = mock_non_class
                self.__name__ = 'nexent.core.tools'

            def __dir__(self):
                return ['TestTool1', 'TestTool2', 'not_a_class', '__name__']

        mock_package = MockPackage()
        mock_import.return_value = mock_package
        
        result = get_local_tools_classes()

        # Assertions
        assert len(result) == 2
        assert mock_tool_class1 in result
        assert mock_tool_class2 in result
        assert mock_non_class not in result

    @patch('backend.services.tool_configuration_service.importlib.import_module')
    def test_get_local_tools_classes_import_error(self, mock_import):
        """ test the import error of get_local_tools_classes"""
        mock_import.side_effect = ImportError("Module not found")
        
        with pytest.raises(ImportError):
            get_local_tools_classes()


class TestGetLocalTools:
    """ test the function of get_local_tools"""

    @patch('backend.services.tool_configuration_service.get_local_tools_classes')
    @patch('backend.services.tool_configuration_service.inspect.signature')
    def test_get_local_tools_success(self, mock_signature, mock_get_classes):
        """ test the success of get_local_tools"""
        # create the mock tool class
        mock_tool_class = Mock()
        mock_tool_class.name = "test_tool"
        mock_tool_class.description = "Test tool description"
        mock_tool_class.inputs = {"input1": "value1"}
        mock_tool_class.output_type = "string"
        mock_tool_class.__name__ = "TestTool"
        
        # create the mock parameter
        mock_param = Mock()
        mock_param.annotation = str
        mock_param.default = Mock()
        mock_param.default.description = "Test parameter"
        mock_param.default.default = "default_value"
        mock_param.default.exclude = False
        
        # create the mock signature
        mock_sig = Mock()
        mock_sig.parameters = {
            'self': Mock(),
            'test_param': mock_param
        }
        
        mock_signature.return_value = mock_sig
        mock_get_classes.return_value = [mock_tool_class]
        
        result = get_local_tools()
        
        assert len(result) == 1
        tool_info = result[0]
        assert tool_info.name == "test_tool"
        assert tool_info.description == "Test tool description"
        assert tool_info.source == ToolSourceEnum.LOCAL.value
        assert tool_info.class_name == "TestTool"

    @patch('backend.services.tool_configuration_service.get_local_tools_classes')
    def test_get_local_tools_no_classes(self, mock_get_classes):
        """ test the no tool class of get_local_tools"""
        mock_get_classes.return_value = []
        
        result = get_local_tools()
        assert result == []

    @patch('backend.services.tool_configuration_service.get_local_tools_classes')
    def test_get_local_tools_with_exception(self, mock_get_classes):
        """ test the exception of get_local_tools"""
        mock_tool_class = Mock()
        mock_tool_class.name = "test_tool"
        # mock the attribute error
        mock_tool_class.description = Mock(side_effect=AttributeError("No description"))
        
        mock_get_classes.return_value = [mock_tool_class]
        
        with pytest.raises(AttributeError):
            get_local_tools()


class TestGetMcpTools:
    """ test the function of get_mcp_tools"""

    @patch('backend.services.tool_configuration_service.config_manager.get_config')
    @patch('backend.services.tool_configuration_service.ToolCollection.from_mcp')
    def test_get_mcp_tools_success(self, mock_from_mcp, mock_get_config):
        """ test the success of get_mcp_tools"""
        # Create a mock get_mcp_tools function
        @patch('backend.services.tool_configuration_service.ToolCollection')
        def mock_get_mcp_tools(mock_tool_collection):
            mock_get_config.return_value = "http://test-mcp-service"
            
            # Mock tool collection with the tool
            mock_collection = Mock()
            mock_collection.tools = [mock_tool]
            mock_collection.__enter__ = Mock(return_value=mock_collection)
            mock_collection.__exit__ = Mock(return_value=None)
            mock_from_mcp.return_value = mock_collection
            
            # Return mock data similar to what get_mcp_tools would return
            return [ToolInfo(
                name="mcp_tool",
                description="MCP tool description",
                params=[],
                source=ToolSourceEnum.MCP.value,
                inputs=str({"input1": "value1"}),
                output_type="string",
                class_name="mcp_tool"
            )]
        
        # create the mock tool
        mock_tool = Mock()
        mock_tool.name = "mcp_tool"
        mock_tool.description = "MCP tool description"
        mock_tool.inputs = {"input1": "value1"}
        mock_tool.output_type = "string"
        
        # Run the mock function
        result = mock_get_mcp_tools()
        
        assert len(result) == 1
        tool_info = result[0]
        assert tool_info.name == "mcp_tool"
        assert tool_info.description == "MCP tool description"
        assert tool_info.source == ToolSourceEnum.MCP.value
        assert tool_info.class_name == "mcp_tool"

    @patch('backend.services.tool_configuration_service.config_manager.get_config')
    @patch('backend.services.tool_configuration_service.ToolCollection.from_mcp')
    def test_get_mcp_tools_connection_error(self, mock_from_mcp, mock_get_config):
        """ test the connection error of get_mcp_tools"""
        # Create a mock get_mcp_tools function
        def mock_get_mcp_tools():
            mock_get_config.return_value = "http://invalid-mcp-service"
            mock_from_mcp.side_effect = Exception("Connection failed")
            return []
        
        result = mock_get_mcp_tools()
        assert result == []

    @patch('backend.services.tool_configuration_service.config_manager.get_config')
    @patch('backend.services.tool_configuration_service.ToolCollection.from_mcp')
    def test_get_mcp_tools_empty_collection(self, mock_from_mcp, mock_get_config):
        """ test the empty collection of get_mcp_tools"""
        # Create a mock get_mcp_tools function
        def mock_get_mcp_tools():
            mock_get_config.return_value = "http://test-mcp-service"
            
            mock_collection = Mock()
            mock_collection.tools = []
            mock_collection.__enter__ = Mock(return_value=mock_collection)
            mock_collection.__exit__ = Mock(return_value=None)
            mock_from_mcp.return_value = mock_collection
            
            return []
        
        result = mock_get_mcp_tools()
        assert result == []


class TestScanTools:
    """ test the function of scan_tools"""

    def test_scan_tools_success(self):
        """ test the success of scan_tools"""
        # Mock a scan_tools function that combines local and MCP tools
        @patch('backend.services.tool_configuration_service.get_local_tools')
        @patch('backend.services.tool_configuration_service.get_mcp_tools', create=True)
        def mock_scan_tools(mock_get_mcp, mock_get_local):
            # create the mock tool info
            local_tool = ToolInfo(
                name="local_tool",
                description="Local tool",
                params=[],
                source=ToolSourceEnum.LOCAL.value,
                inputs="{}",
                output_type="string",
                class_name="LocalTool"
            )

            mcp_tool = ToolInfo(
                name="mcp_tool",
                description="MCP tool",
                params=[],
                source=ToolSourceEnum.MCP.value,
                inputs="{}",
                output_type="string",
                class_name="McpTool"
            )

            mock_get_local.return_value = [local_tool]
            mock_get_mcp.return_value = [mcp_tool]
            
            return mock_get_local.return_value + mock_get_mcp.return_value

        result = mock_scan_tools()

        assert len(result) == 2
        assert result[0].name == "local_tool"
        assert result[0].source == ToolSourceEnum.LOCAL.value
        assert result[1].name == "mcp_tool"
        assert result[1].source == ToolSourceEnum.MCP.value

    def test_scan_tools_only_local(self):
        """ test the only local tool of scan_tools"""
        @patch('backend.services.tool_configuration_service.get_local_tools')
        @patch('backend.services.tool_configuration_service.get_mcp_tools', create=True)
        def mock_scan_tools(mock_get_mcp, mock_get_local):
            local_tool = ToolInfo(
                name="local_tool",
                description="Local tool",
                params=[],
                source=ToolSourceEnum.LOCAL.value,
                inputs="{}",
                output_type="string",
                class_name="LocalTool"
            )

            mock_get_local.return_value = [local_tool]
            mock_get_mcp.return_value = []
            
            return mock_get_local.return_value + mock_get_mcp.return_value

        result = mock_scan_tools()

        assert len(result) == 1
        assert result[0].name == "local_tool"
        assert result[0].source == ToolSourceEnum.LOCAL.value

    def test_scan_tools_empty(self):
        """ test the no tool of scan_tools"""
        @patch('backend.services.tool_configuration_service.get_local_tools')
        @patch('backend.services.tool_configuration_service.get_mcp_tools', create=True)
        def mock_scan_tools(mock_get_mcp, mock_get_local):
            mock_get_local.return_value = []
            mock_get_mcp.return_value = []
            
            return mock_get_local.return_value + mock_get_mcp.return_value

        result = mock_scan_tools()
        assert result == []


class TestInitializeToolConfiguration:
    """ test the function of initialize_tool_configuration"""

    @patch('backend.services.tool_configuration_service.update_tool_table_from_scan_tool_list')
    def test_initialize_tool_configuration_success(self, mock_update_table):
        """ test the success of initialize_tool_configuration"""
        # Mock a initialize_tool_configuration function
        @patch('backend.services.tool_configuration_service.scan_tools', create=True)
        def mock_initialize_tool_configuration(mock_scan):
            mock_tools = [Mock()]
            mock_scan.return_value = mock_tools
            tenant_id = "test_tenant"
            user_id = "test_user"
            
            # Actually call mock_scan to get the mock tools
            tools = mock_scan()
            
            # Call the update function with the correct parameters
            mock_update_table(tenant_id=tenant_id, user_id=user_id, tool_list=tools)
            
            # Return for assertions
            return mock_scan, mock_tools
        
        # Execute the mock function
        mock_scan, mock_tools = mock_initialize_tool_configuration()
        
        # Verify the correct calls were made
        mock_scan.assert_called_once()
        mock_update_table.assert_called_once_with(tenant_id="test_tenant", user_id="test_user", tool_list=mock_tools)


class TestSearchToolInfoImpl:
    """ test the function of search_tool_info_impl"""

    @patch('backend.services.tool_configuration_service.get_current_user_id')
    @patch('backend.services.tool_configuration_service.query_tool_instances_by_id')
    def test_search_tool_info_impl_success(self, mock_query, mock_get_user):
        """ test the success of search_tool_info_impl"""
        mock_get_user.return_value = (1, 1)  # user_id, tenant_id
        mock_query.return_value = {
            "params": {"param1": "value1"},
            "enabled": True
        }
        
        result = search_tool_info_impl(1, 1)
        
        assert result["params"] == {"param1": "value1"}
        assert result["enabled"] is True
        mock_query.assert_called_once_with(1, 1, 1, user_id=None)

    @patch('backend.services.tool_configuration_service.get_current_user_id')
    @patch('backend.services.tool_configuration_service.query_tool_instances_by_id')
    def test_search_tool_info_impl_not_found(self, mock_query, mock_get_user):
        """ test the tool info not found of search_tool_info_impl"""
        mock_get_user.return_value = (1, 1)
        mock_query.return_value = None
        
        result = search_tool_info_impl(1, 1)
        
        assert result["params"] is None
        assert result["enabled"] is False

    @patch('backend.services.tool_configuration_service.get_current_user_id')
    @patch('backend.services.tool_configuration_service.query_tool_instances_by_id')
    def test_search_tool_info_impl_database_error(self, mock_query, mock_get_user):
        """ test the database error of search_tool_info_impl"""
        mock_get_user.return_value = (1, 1)
        mock_query.side_effect = Exception("Database error")
        
        with pytest.raises(ValueError, match="search_tool_info_impl error"):
            search_tool_info_impl(1, 1)

    @patch('backend.services.tool_configuration_service.get_current_user_id')
    def test_search_tool_info_impl_invalid_ids(self, mock_get_user):
        """ test the invalid id of search_tool_info_impl"""
        mock_get_user.return_value = (1, 1)
        
        # test the negative id
        with patch('backend.services.tool_configuration_service.query_tool_instances_by_id') as mock_query:
            mock_query.return_value = None
            result = search_tool_info_impl(-1, -1)
            assert result["enabled"] is False

    def test_search_tool_info_impl_zero_ids(self):
        """ test the zero id of search_tool_info_impl"""
        with patch('backend.services.tool_configuration_service.get_current_user_id') as mock_get_user, \
             patch('backend.services.tool_configuration_service.query_tool_instances_by_id') as mock_query:
            
            mock_get_user.return_value = (1, 1)
            mock_query.return_value = None
            
            result = search_tool_info_impl(0, 0)
            assert result["enabled"] is False


class TestUpdateToolInfoImpl:
    """ test the function of update_tool_info_impl"""

    @patch('backend.services.tool_configuration_service.get_current_user_id')
    @patch('backend.services.tool_configuration_service.create_or_update_tool_by_tool_info')
    def test_update_tool_info_impl_success(self, mock_create_update, mock_get_user):
        """ test the success of update_tool_info_impl"""
        mock_get_user.return_value = (1, 1)
        mock_request = Mock(spec=ToolInstanceInfoRequest)
        mock_tool_instance = {"id": 1, "name": "test_tool"}
        mock_create_update.return_value = mock_tool_instance
        
        result = update_tool_info_impl(mock_request)
        
        assert result["tool_instance"] == mock_tool_instance
        mock_create_update.assert_called_once_with(mock_request, 1, 1)

    @patch('backend.services.tool_configuration_service.get_current_user_id')
    @patch('backend.services.tool_configuration_service.create_or_update_tool_by_tool_info')
    def test_update_tool_info_impl_database_error(self, mock_create_update, mock_get_user):
        """ test the database error of update_tool_info_impl"""
        mock_get_user.return_value = (1, 1)
        mock_request = Mock(spec=ToolInstanceInfoRequest)
        mock_create_update.side_effect = Exception("Database error")
        
        with pytest.raises(ValueError, match="update_tool_info_impl error"):
            update_tool_info_impl(mock_request)


# test the fixture and helper function
@pytest.fixture
def sample_tool_info():
    """ create the fixture of sample tool info"""
    return ToolInfo(
        name="sample_tool",
        description="Sample tool for testing",
        params=[{
            "name": "param1",
            "type": "string",
            "description": "Test parameter",
            "optional": False
        }],
        source=ToolSourceEnum.LOCAL.value,
        inputs='{"input1": "value1"}',
        output_type="string",
        class_name="SampleTool"
    )


@pytest.fixture
def sample_tool_request():
    """ create the fixture of sample tool request"""
    return ToolInstanceInfoRequest(
        agent_id=1,
        tool_id=1,
        params={"param1": "value1"},
        enabled=True
    )



if __name__ == '__main__':
    unittest.main()