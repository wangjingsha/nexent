from typing import List

from threading import Event
from smolagents import ActionStep, TaskStep, AgentText, handle_agent_output_types
from ..utils.observer import ProcessType
from .agent_model import ModelConfig, ToolConfig, AgentConfig, AgentHistory
from ..utils.observer import MessageObserver
from ..models.openai_llm import OpenAIModel
from .core_agent import CoreAgent
from ..tools import *  # Used for tool creation, do not delete!!!

class NexentAgent:
    def __init__(self, observer: MessageObserver,
                 model_config_list: List[ModelConfig],
                 stop_event: Event,
                 mcp_tool_collection=None):
        """
        init the agent create factory

        Args:
            mcp_tool_collection:
            observer:
            model_config_list:
        """
        if not isinstance(observer, MessageObserver):
            raise TypeError("Create Observer Object with MessageObserver")

        self.observer = observer
        self.model_config_list = model_config_list
        self.stop_event = stop_event
        self.mcp_tool_collection = mcp_tool_collection

        self.agent = None


    def create_model(self, model_cite_name: str):
        """create a model instance"""
        model_config = next(model_config for model_config in self.model_config_list if model_config.cite_name == model_cite_name)
        if model_config is None:
            raise ValueError(f"Model {model_cite_name} not found")
        model = OpenAIModel(
            observer=self.observer,
            model_id=model_config.model_name,
            api_key=model_config.api_key,
            api_base=model_config.url,
            temperature=model_config.temperature,
            top_p=model_config.top_p
        )
        model.stop_event = self.stop_event
        return model

    def create_local_tool(self, tool_config: ToolConfig):
        class_name = tool_config.class_name
        params = tool_config.params
        tool_class = globals().get(class_name)
        if tool_class is None:
            raise ValueError(f"{class_name} not found in local")
        else:


            if class_name == "KnowledgeBaseSearchTool":
                tools_obj = tool_class(index_names=tool_config.metadata.get("index_names", []),
                                       observer= self.observer,
                                       es_core=tool_config.metadata.get("es_core", []),
                                       embedding_model=tool_config.metadata.get("embedding_model", []),
                                       **params)
            else:
                tools_obj = tool_class(**params)
                if hasattr(tools_obj, 'observer'):
                    tools_obj.observer = self.observer
            return tools_obj

    def create_mcp_tool(self, class_name):
        if self.mcp_tool_collection is None:
            raise ValueError("MCP tool collection is not initialized")
        tool_obj = next(
            (tool for tool in self.mcp_tool_collection.tools if tool.name == class_name),
            None
        )
        if tool_obj is None:
            raise ValueError(f"{class_name} not found in MCP server")
        return tool_obj

    def create_tool(self, tool_config: ToolConfig):
        """create a tool instance according to the tool config"""
        if not isinstance(tool_config, ToolConfig):
            raise TypeError("tool_config must be a ToolConfig object")
        try:
            class_name = tool_config.class_name
            source = tool_config.source

            if source == "local":
                tool_obj = self.create_local_tool(tool_config)
            elif source == "mcp":
                tool_obj = self.create_mcp_tool(class_name)
            else:
                raise ValueError(f"unsupported tool source: {source}")
            return tool_obj
        except Exception as e:
            raise ValueError(f"Error in creating tool: {e}")

    def create_single_agent(self, agent_config: AgentConfig):
        if not isinstance(agent_config, AgentConfig):
            raise TypeError("agent_config must be a AgentConfig object")

        try:
            model = self.create_model(agent_config.model_name)
            prompt_templates = agent_config.prompt_templates

            try:
                tool_list = [self.create_tool(tool_config) for tool_config in agent_config.tools]
            except Exception as e:
                raise ValueError(f"Error in creating tool: {e}")

            try:
                managed_agents_list = [self.create_single_agent(sub_agent_config) for sub_agent_config in agent_config.managed_agents]
            except Exception as e:
                raise ValueError(f"Error in creating managed agent: {e}")

            # create the agent
            agent = CoreAgent(
                observer=self.observer,
                tools=tool_list,
                model=model,
                name=agent_config.name,
                description=agent_config.description,
                max_steps=agent_config.max_steps,
                prompt_templates=prompt_templates,
                provide_run_summary=agent_config.provide_run_summary,
                managed_agents=managed_agents_list
            )
            agent.stop_event = self.stop_event

            return agent
        except Exception as e:
            raise ValueError(f"Error in creating agent, agent name: {agent_config.name}, Error: {e}")

    def add_history_to_agent(self, history: List[AgentHistory]):
        """
        Add conversation history to agent's memory

        Args:
            history: List of conversation messages with role and content
        """
        if history is None:
            return

        if not isinstance(self.agent, CoreAgent):
            raise TypeError(f"agent must be a CoreAgent object, not {type(self.agent)}")

        if not all(isinstance(msg, AgentHistory) for msg in history):
            raise TypeError("history must be a list of AgentHistory objects")

        self.agent.memory.reset()
        # Add conversation history to memory sequentially
        for msg in history:
            if msg.role == 'user':
                # Create task step for user message
                self.agent.memory.steps.append(TaskStep(task=msg.content))
            elif msg.role == 'assistant':
                self.agent.memory.steps.append(ActionStep(action_output=msg.content, model_output=msg.content))

    def agent_run_with_observer(self, query: str, reset=True):
        if not isinstance(self.agent, CoreAgent):
            raise TypeError(f"agent must be a CoreAgent object, not {type(self.agent)}")

        observer = self.agent.observer
        try:
            for step_log in self.agent.run(query, stream=True, reset=reset):
                # Add content to observer
                if not isinstance(step_log, ActionStep):
                    continue
                # Keep duration
                if hasattr(step_log, "duration"):
                    observer.add_message("", ProcessType.TOKEN_COUNT, str(round(float(step_log.duration), 2)))

                if hasattr(step_log, "error") and step_log.error is not None:
                    observer.add_message("", ProcessType.ERROR, str(step_log.error))

            final_answer = step_log  # Last log is the run's final_answer
            final_answer = handle_agent_output_types(final_answer)

            if isinstance(final_answer, AgentText):
                observer.add_message(self.agent.agent_name, ProcessType.FINAL_ANSWER, final_answer.to_string())
            else:
                observer.add_message(self.agent.agent_name, ProcessType.FINAL_ANSWER, str(final_answer))

            # Check if we need to stop from external stop_event
            if self.agent.stop_event.is_set():
                observer.add_message(self.agent.agent_name, ProcessType.ERROR,
                                     "Agent execution interrupted by external stop signal")
        except Exception as e:
            observer.add_message(agent_name=self.agent.agent_name, process_type=ProcessType.ERROR,
                                 content=f"Error in interaction: {str(e)}")
            raise ValueError(f"Error in interaction: {str(e)}")

    def set_agent(self, agent: CoreAgent):
        if not isinstance(agent, CoreAgent):
            raise TypeError(f"agent must be a CoreAgent object, not {type(agent)}")
        self.agent = agent
