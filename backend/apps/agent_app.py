import logging
from typing import Optional

from fastapi import HTTPException, APIRouter, Header, Request
from fastapi.responses import StreamingResponse
from nexent.core.agents.run_agent import agent_run

from utils.auth_utils import get_current_user_info
from agents.create_agent_info import create_agent_run_info
from consts.model import AgentRequest, AgentInfoRequest, AgentIDRequest, ConversationResponse, AgentImportRequest
from services.agent_service import list_main_agent_info_impl, get_agent_info_impl, \
    get_creating_sub_agent_info_impl, update_agent_info_impl, delete_agent_impl, export_agent_impl, import_agent_impl
from services.conversation_management_service import save_conversation_user, save_conversation_assistant
from utils.config_utils import config_manager
from utils.thread_utils import submit
from agents.agent_run_manager import agent_run_manager


router = APIRouter(prefix="/agent")
# Configure logging
logger = logging.getLogger("agent_app")

# Define API route
@router.post("/run")
async def agent_run_api(agent_request: AgentRequest, http_request: Request, authorization: str = Header(None)):
    """
    Agent execution API endpoint
    """
    _, _, language = get_current_user_info(authorization, http_request)
    agent_run_info = await create_agent_run_info(agent_id=agent_request.agent_id,
                                                 minio_files=agent_request.minio_files,
                                                 query=agent_request.query,
                                                 history=agent_request.history,
                                                 authorization=authorization,
                                                 language=language)

    agent_run_manager.register_agent_run(agent_request.conversation_id, agent_run_info)
    # Save user message only if not in debug mode
    if not agent_request.is_debug:
        submit(save_conversation_user, agent_request, authorization)

    async def generate():
        messages = []
        try:
            async for chunk in agent_run(agent_run_info):
                messages.append(chunk)
                yield f"data: {chunk}\n\n"
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Agent run error: {str(e)}")
        finally:
            # Save assistant message only if not in debug mode
            if not agent_request.is_debug:
                submit(save_conversation_assistant, agent_request, messages, authorization)
            # Unregister agent run instance for both debug and non-debug modes
            agent_run_manager.unregister_agent_run(agent_request.conversation_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@router.get("/stop/{conversation_id}")
async def agent_stop_api(conversation_id: int):
    """
    stop agent run for specified conversation_id
    """
    success = agent_run_manager.stop_agent_run(conversation_id)
    if success:
        return {"status": "success", "message": f"successfully stopped agent run for conversation_id {conversation_id}"}
    else:
        raise HTTPException(status_code=404, detail=f"no running agent found for conversation_id {conversation_id}")

# Add configuration reload API
@router.post("/reload_config")
async def reload_config():
    """
    Manually trigger configuration reload
    """
    return config_manager.force_reload()


@router.get("/list")
async def list_main_agent_info_api(authorization: str = Header(None)):
    """
    List all agents, create if the main Agent cannot be found.
    """
    try:
        return list_main_agent_info_impl(authorization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent list error: {str(e)}")


@router.post("/search_info")
async def search_agent_info_api(request: AgentInfoRequest, authorization: Optional[str] = Header(None)):
    """
    Search agent info by agent_id
    """
    try:
        return get_agent_info_impl(request.agent_id, authorization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent search info error: {str(e)}")


@router.post("/get_creating_sub_agent_id")
async def get_creating_sub_agent_info_api(request: AgentIDRequest, authorization: Optional[str] = Header(None)):
    """
    Create a new sub agent, return agent_ID
    """
    try:
        return get_creating_sub_agent_info_impl(request.agent_id, authorization)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent create error: {str(e)}")


@router.post("/update")
async def update_agent_info_api(request: AgentInfoRequest, authorization: Optional[str] = Header(None)):
    """
    Update an existing agent
    """
    try:
        update_agent_info_impl(request, authorization)
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent update error: {str(e)}")


@router.delete("")
async def delete_agent_api(request: AgentIDRequest, authorization: Optional[str] = Header(None)):
    """
    Delete an agent
    """
    try:
        delete_agent_impl(request.agent_id, authorization)
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent delete error: {str(e)}")


@router.post("/export")
async def export_agent_api(request: AgentIDRequest, authorization: Optional[str] = Header(None)):
    """
    export an agent
    """
    try:
        agent_info_str = await export_agent_impl(request.agent_id, authorization)
        return ConversationResponse(code=0, message="success", data=agent_info_str)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent export error: {str(e)}")


@router.post("/import")
async def import_agent_api(request: AgentImportRequest, authorization: Optional[str] = Header(None)):
    """
    import an agent
    """
    try:
        import_agent_impl(request.agent_id, request.agent_info, authorization)
        return {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent import error: {str(e)}")
    