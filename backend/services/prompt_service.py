import logging
import queue
import threading

import yaml
from jinja2 import StrictUndefined, Template
from smolagents import OpenAIServerModel

from consts.model import AgentInfoRequest
from database.agent_db import update_agent, \
    query_tools_by_ids, query_sub_agents_id_list, search_agent_info_by_agent_id
from services.agent_service import get_enable_tool_id_by_agent_id
from utils.prompt_template_utils import get_prompt_generate_prompt_template
from utils.config_utils import tenant_config_manager, get_model_name_from_config
from utils.auth_utils import get_current_user_info
from fastapi import Header, Request

from utils.str_utils import remove_think_tags, add_no_think_token

# Configure logging
logger = logging.getLogger("prompt_service")


def call_llm_for_system_prompt(user_prompt: str, system_prompt: str, callback=None, tenant_id: str = None) -> str:
    """
    Call LLM to generate system prompt

    Args:
        user_prompt: description of the current task
        system_prompt: system prompt for the LLM

    Returns:
        str: Generated system prompt
    """
    llm_model_config = tenant_config_manager.get_model_config(key="LLM_ID", tenant_id=tenant_id)

    llm = OpenAIServerModel(
        model_id=get_model_name_from_config(llm_model_config) if llm_model_config else "",
        api_base=llm_model_config.get("base_url", ""),
        api_key=llm_model_config.get("api_key", ""),
        temperature=0.3,
        top_p=0.95
    )
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}]
    add_no_think_token(messages)
    try:
        completion_kwargs = llm._prepare_completion_kwargs(
            messages=messages,
            model=llm.model_id,
            temperature=0.3,
            top_p=0.95
        )
        current_request = llm.client.chat.completions.create(stream=True, **completion_kwargs)
        token_join = []
        for chunk in current_request:
            new_token = chunk.choices[0].delta.content
            if new_token is not None:
                new_token = remove_think_tags(new_token)
                token_join.append(new_token)
                current_text = "".join(token_join)
                if callback is not None:
                    callback(current_text)
        return "".join(token_join)
    except Exception as e:
        logger.error(f"Failed to generate prompt from LLM: {str(e)}")
        raise e


def generate_and_save_system_prompt_impl(agent_id: int, task_description: str, authorization: str = Header(None),
                                         request: Request = None):
    user_id, tenant_id, language = get_current_user_info(authorization, request)

    # Get description of tool and agent
    tool_info_list = get_enabled_tool_description_for_generate_prompt(
        tenant_id=tenant_id, agent_id=agent_id, user_id=user_id
    )
    sub_agent_info_list = get_enabled_sub_agent_description_for_generate_prompt(
        tenant_id=tenant_id, agent_id=agent_id, user_id=user_id
    )

    # 1. Real-time streaming push
    final_results = {"duty": "", "constraint": "", "few_shots": "", "agent_var_name": "", "agent_display_name": "",
                     "agent_description": ""}
    for result_data in generate_system_prompt(sub_agent_info_list, task_description, tool_info_list, tenant_id,
                                              language):
        # Update final results
        final_results[result_data["type"]] = result_data["content"]
        yield result_data

    # 2. Update agent with the final result
    logger.info("Updating agent with business_description and prompt segments")
    agent_info = AgentInfoRequest(
        agent_id=agent_id,
        business_description=task_description,
        duty_prompt=final_results["duty"],
        constraint_prompt=final_results["constraint"],
        few_shots_prompt=final_results["few_shots"],
        name=final_results["agent_var_name"],
        display_name=final_results["agent_display_name"],
        description=final_results["agent_description"]
    )
    update_agent(
        agent_id=agent_id,
        agent_info=agent_info,
        tenant_id=tenant_id,
        user_id=user_id
    )
    logger.info("Prompt generation and agent update completed successfully")


def generate_system_prompt(sub_agent_info_list, task_description, tool_info_list, tenant_id: str, language: str = 'zh'):
    prompt_for_generate = get_prompt_generate_prompt_template(language)

    # Add app information to the template variables
    content = join_info_for_generate_system_prompt(prompt_for_generate, sub_agent_info_list, task_description,
                                                   tool_info_list)

    def make_callback(tag):
        def callback_fn(current_text):
            latest[tag] = current_text
            # Notify main thread that new content is available
            produce_queue.put(tag)

        return callback_fn

    def run_and_flag(tag, sys_prompt):
        try:
            call_llm_for_system_prompt(content, sys_prompt, make_callback(tag), tenant_id)
        except Exception as e:
            logger.error(f"Error in {tag} generation: {e}")
        finally:
            stop_flags[tag] = True

    produce_queue = queue.Queue()
    latest = {"duty": "", "constraint": "", "few_shots": "", "agent_var_name": "", "agent_display_name": "",
              "agent_description": ""}
    stop_flags = {"duty": False, "constraint": False, "few_shots": False, "agent_var_name": False,
                  "agent_display_name": False, "agent_description": False}

    threads = []
    logger.info(f"Generating system prompt")
    for tag, sys_prompt in [
        ("duty", prompt_for_generate["DUTY_SYSTEM_PROMPT"]),
        ("constraint", prompt_for_generate["CONSTRAINT_SYSTEM_PROMPT"]),
        ("few_shots", prompt_for_generate["FEW_SHOTS_SYSTEM_PROMPT"]),
        ("agent_var_name", prompt_for_generate["AGENT_VARIABLE_NAME_SYSTEM_PROMPT"]),
        ("agent_display_name", prompt_for_generate["AGENT_DISPLAY_NAME_SYSTEM_PROMPT"]),
        ("agent_description", prompt_for_generate["AGENT_DESCRIPTION_SYSTEM_PROMPT"])
    ]:
        t = threading.Thread(target=run_and_flag, args=(tag, sys_prompt))
        t.start()
        threads.append(t)

    # Directly stream output of three sections
    last_results = {"duty": "", "constraint": "", "few_shots": "", "agent_var_name": "", "agent_display_name": "",
                    "agent_description": ""}
    while not all(stop_flags.values()):
        try:
            produce_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        # Check if there is new content
        for tag in ["duty", "constraint", "few_shots"]:
            if latest[tag] != last_results[tag]:
                # Build return data structure
                result_data = {
                    "type": tag,
                    "content": latest[tag],
                    "is_complete": stop_flags[tag]
                }
                yield result_data
                last_results[tag] = latest[tag]

    # Wait for all threads to complete
    for t in threads:
        t.join(timeout=5)

    for tag in ["duty", "constraint", "few_shots", "agent_var_name", "agent_display_name", "agent_description"]:
        if stop_flags[tag]:
            if tag in {'agent_var_name', 'agent_display_name', 'agent_description'}:
                latest[tag] = latest[tag].strip().replace('\n', '')
            result_data = {
                "type": tag,
                "content": latest[tag],
                "is_complete": True
            }
            yield result_data
            last_results[tag] = latest[tag]


def join_info_for_generate_system_prompt(prompt_for_generate, sub_agent_info_list, task_description, tool_info_list,
                                         app_name=None, app_description=None):
    tool_description = "\n".join(
        [f"- {tool['name']}: {tool['description']} \n 接受输入: {tool['inputs']}\n 返回输出类型: {tool['output_type']}"
         for tool in tool_info_list])
    agent_description = "\n".join(
        [f"- {sub_agent_info['name']}: {sub_agent_info['description']}" for sub_agent_info in sub_agent_info_list])
    # Generate content using template
    content = Template(prompt_for_generate["USER_PROMPT"], undefined=StrictUndefined).render({
        "tool_description": tool_description,
        "agent_description": agent_description,
        "task_description": task_description,
        "APP_NAME": app_name,
        "APP_DESCRIPTION": app_description
    })
    return content


def get_enabled_tool_description_for_generate_prompt(agent_id: int, tenant_id: str, user_id: str = None):
    # Get tool information
    logger.info("Fetching tool instances")
    tool_id_list = get_enable_tool_id_by_agent_id(agent_id=agent_id, tenant_id=tenant_id, user_id=user_id)
    tool_info_list = query_tools_by_ids(tool_id_list)
    return tool_info_list


def get_enabled_sub_agent_description_for_generate_prompt(agent_id: int, tenant_id: str, user_id: str = None):
    logger.info("Fetching sub-agents information")

    sub_agent_id_list = query_sub_agents_id_list(main_agent_id=agent_id, tenant_id=tenant_id)

    sub_agent_info_list = []
    for sub_agent_id in sub_agent_id_list:
        sub_agent_info = search_agent_info_by_agent_id(agent_id=sub_agent_id, tenant_id=tenant_id)

        sub_agent_info_list.append(sub_agent_info)
    return sub_agent_info_list


def fine_tune_prompt(system_prompt: str, command: str, tenant_id: str, language: str = 'zh'):
    logger.info("Starting prompt fine-tuning")

    try:
        fine_tune_config_path = 'backend/prompts/utils/prompt_fine_tune_en.yaml' if language == 'en' else 'backend/prompts/utils/prompt_fine_tune.yaml'

        with open(fine_tune_config_path, "r", encoding="utf-8") as f:
            prompt_for_fine_tune = yaml.safe_load(f)

        content = Template(prompt_for_fine_tune["FINE_TUNE_USER_PROMPT"], undefined=StrictUndefined).render({
            "prompt": system_prompt,
            "command": command
        })

        logger.info("Calling LLM for prompt fine-tuning")
        regenerate_prompt = call_llm_for_system_prompt(
            user_prompt=content,
            system_prompt=prompt_for_fine_tune["FINE_TUNE_SYSTEM_PROMPT"],
            tenant_id=tenant_id
        )
        logger.info("Successfully completed prompt fine-tuning")
        return regenerate_prompt

    except Exception as e:
        logger.error(f"Error in prompt fine-tuning process: {str(e)}")
        raise e
