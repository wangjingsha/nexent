import { Tool, convertParamType } from '@/types/agentAndToolConst';
import { API_ENDPOINTS } from './api';
import { getAuthHeaders } from '@/lib/auth';

/**
 * get tool list from backend
 * @returns converted tool list
 */
export const fetchTools = async () => {
  try {
    const response = await fetch(API_ENDPOINTS.tool.list, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }
    const data = await response.json();
    
    // convert backend Tool format to frontend Tool format
    const formattedTools = data.map((tool: any) => ({
      id: String(tool.tool_id),
      name: tool.name,
      description: tool.description,
      source: tool.source,
      is_available: tool.is_available,
      create_time: tool.create_time,
      initParams: tool.params.map((param: any) => {
        return {
          name: param.name,
          type: convertParamType(param.type),
          required: !param.optional,
          value: param.default,
          description: param.description
        };
      })
    }));
    
    return {
      success: true,
      data: formattedTools,
      message: ''
    };
  } catch (error) {
    console.error('获取工具列表出错:', error);
    return {
      success: false,
      data: [],
      message: '获取工具列表失败，请稍后重试'
    };
  }
};

/**
 * get agent list from backend
 * @returns object containing main_agent_id and sub_agent_list
 */
export const fetchAgentList = async () => {
  try {
    const response = await fetch(API_ENDPOINTS.agent.list, {
      headers: getAuthHeaders(),
    });
    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }
    const data = await response.json();
    
    // convert backend data to frontend format
    const formattedAgents = data.sub_agent_list.map((agent: any) => ({
      id: agent.agent_id,
      name: agent.name,
      description: agent.description,
      modelName: agent.model_name,
      max_step: agent.max_steps,
      prompt: agent.prompt,
      business_description: agent.business_description,
      parentAgentId: agent.parent_agent_id,
      enabled: agent.enabled,
      is_available: agent.is_available,
      createTime: agent.create_time,
      updateTime: agent.update_time,
      tools: agent.tools ? agent.tools.map((tool: any) => {
        const params = typeof tool.params === 'string' ? JSON.parse(tool.params) : tool.params;
        return {
          id: tool.tool_id,
          name: tool.name,
          description: tool.description,
          source: tool.source,
          is_available: tool.is_available,
          initParams: Array.isArray(params) ? params.map((param: any) => ({
            name: param.name,
            type: convertParamType(param.type),
            required: !param.optional,
            value: param.default,
            description: param.description
          })) : []
        };
      }) : [],
      provide_run_summary: agent.provide_run_summary
    }));
    
    return {
      success: true,
      data: {
        mainAgentId: data.main_agent_id,
        subAgentList: formattedAgents,
        enabledToolIds: data.enable_tool_id_list || [],
        enabledAgentIds: data.enable_agent_id_list || [],
        modelName: data.model_name,
        maxSteps: data.max_steps,
        businessDescription: data.business_description,
        prompt: data.prompt
      },
      message: ''
    };
  } catch (error) {
    console.error('获取 agent 列表失败:', error);
    return {
      success: false,
      data: {
        mainAgentId: null,
        subAgentList: [],
        enabledToolIds: [],
        enabledAgentIds: [],
        modelName: null,
        maxSteps: null,
        businessDescription: null,
        prompt: null
      },
      message: '获取 agent 列表失败，请稍后重试'
    };
  }
};

/**
 * get creating sub agent id
 * @param mainAgentId current main agent id
 * @returns new sub agent id
 */
export const getCreatingSubAgentId = async (mainAgentId: string | null) => {
  try {
    const response = await fetch(API_ENDPOINTS.agent.getCreatingSubAgentId, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ agent_id: mainAgentId }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    return {
      success: true,
      data: {
        agentId: data.agent_id,
        enabledToolIds: data.enable_tool_id_list || [],
        modelName: data.model_name,
        maxSteps: data.max_steps,
        businessDescription: data.business_description,
        prompt: data.prompt
      },
      message: ''
    };
  } catch (error) {
    console.error('获取创建子代理ID失败:', error);
    return {
      success: false,
      data: null,
      message: '获取创建子代理ID失败，请稍后重试'
    };
  }
};

/**
 * update tool config
 * @param toolId tool id
 * @param agentId agent id
 * @param params tool params config
 * @param enable whether enable tool
 * @returns update result
 */
export const updateToolConfig = async (
  toolId: number,
  agentId: number,
  params: Record<string, any>,
  enable: boolean
) => {
  try {
    console.log({"tool_id":toolId, "agent_id":agentId, "params":params, "enabled":enable})

    const response = await fetch(API_ENDPOINTS.tool.update, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        tool_id: toolId,
        agent_id: agentId,
        params: params,
        enabled: enable
      }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    return {
      success: true,
      data: data,
      message: '工具配置更新成功'
    };
  } catch (error) {
    console.error('更新工具配置失败:', error);
    return {
      success: false,
      data: null,
      message: '更新工具配置失败，请稍后重试'
    };
  }
};

/**
 * search tool config
 * @param toolId tool id
 * @param agentId agent id
 * @returns tool config info
 */
export const searchToolConfig = async (toolId: number, agentId: number) => {
  try {
    const response = await fetch(API_ENDPOINTS.tool.search, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        tool_id: toolId,
        agent_id: agentId
      }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    return {
      success: true,
      data: {
        params: data.params,
        enabled: data.enabled
      },
      message: ''
    };
  } catch (error) {
    console.error('搜索工具配置失败:', error);
    return {
      success: false,
      data: null,
      message: '搜索工具配置失败，请稍后重试'
    };
  }
};

/**
 * 更新 Agent 信息
 * @param agentId agent id
 * @param name agent 名称
 * @param description agent 描述
 * @param modelName 模型名称
 * @param maxSteps 最大步骤数
 * @param provideRunSummary 是否提供运行摘要
 * @param prompt 系统提示词
 * @returns 更新结果
 */
export const updateAgent = async (
  agentId: number,
  name?: string,
  description?: string,
  modelName?: string,
  maxSteps?: number,
  provideRunSummary?: boolean,
  prompt?: string,
  enabled?: boolean,
  businessDescription?: string
) => {
  try {
    const response = await fetch(API_ENDPOINTS.agent.update, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        agent_id: agentId,
        name: name,
        description: description,
        model_name: modelName,
        max_steps: maxSteps,
        provide_run_summary: provideRunSummary,
        prompt: prompt,
        enabled: enabled,
        business_description: businessDescription
      }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    return {
      success: true,
      data: data,
      message: 'Agent 更新成功'
    };
  } catch (error) {
    console.error('更新 Agent 失败:', error);
    return {
      success: false,
      data: null,
      message: '更新 Agent 失败，请稍后重试'
    };
  }
};

/**
 * 删除 Agent
 * @param agentId agent id
 * @returns 删除结果
 */
export const deleteAgent = async (agentId: number) => {
  try {
    const response = await fetch(API_ENDPOINTS.agent.delete, {
      method: 'DELETE',
      headers: getAuthHeaders(),
      body: JSON.stringify({ agent_id: agentId }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    return {
      success: true,
      message: 'Agent 删除成功'
    };
  } catch (error) {
    console.error('删除 Agent 失败:', error);
    return {
      success: false,
      message: '删除 Agent 失败，请稍后重试'
    };
  }
};

/**
 * export agent configuration
 * @param agentId agent id to export
 * @returns export result
 */
export const exportAgent = async (agentId: number) => {
  try {
    const response = await fetch(API_ENDPOINTS.agent.export, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ agent_id: agentId }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    
    if (data.code === 0) {
      return {
        success: true,
        data: data.data,
        message: data.message
      };
    } else {
      return {
        success: false,
        data: null,
        message: data.message || '导出失败'
      };
    }
  } catch (error) {
    console.error('导出 Agent 失败:', error);
    return {
      success: false,
      data: null,
      message: '导出失败，请稍后重试'
    };
  }
};

/**
 * import agent configuration
 * @param agentId main agent id
 * @param agentInfo agent configuration data
 * @returns import result
 */
export const importAgent = async (agentId: string, agentInfo: any) => {
  try {
    const response = await fetch(API_ENDPOINTS.agent.import, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ 
        agent_id: agentId, 
        agent_info: agentInfo 
      }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    return {
      success: true,
      data: data,
      message: 'Agent 导入成功'
    };
  } catch (error) {
    console.error('导入 Agent 失败:', error);
    return {
      success: false,
      data: null,
      message: '导入 Agent 失败，请稍后重试'
    };
  }
};

/**
 * search agent info by agent id
 * @param agentId agent id
 * @returns agent detail info
 */
export const searchAgentInfo = async (agentId: number) => {
  try {
    const response = await fetch(API_ENDPOINTS.agent.searchInfo, {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ agent_id: agentId }),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    
    // convert backend data to frontend format
    const formattedAgent = {
      id: data.agent_id,
      name: data.name,
      description: data.description,
      model: data.model_name,
      max_step: data.max_steps,
      prompt: data.prompt,
      business_description: data.business_description,
      provide_run_summary: data.provide_run_summary,
      enabled: data.enabled,
      is_available: data.is_available,
      tools: data.tools ? data.tools.map((tool: any) => {
        const params = typeof tool.params === 'string' ? JSON.parse(tool.params) : tool.params;
        return {
          id: String(tool.tool_id),
          name: tool.name,
          description: tool.description,
          source: tool.source,
          is_available: tool.is_available,
          initParams: Array.isArray(params) ? params.map((param: any) => ({
            name: param.name,
            type: convertParamType(param.type),
            required: !param.optional,
            value: param.default,
            description: param.description
          })) : []
        };
      }) : []
    };

    return {
      success: true,
      data: formattedAgent,
      message: ''
    };
  } catch (error) {
    console.error('获取Agent详情失败:', error);
    return {
      success: false,
      data: null,
      message: '获取Agent详情失败，请稍后重试'
    };
  }
};
