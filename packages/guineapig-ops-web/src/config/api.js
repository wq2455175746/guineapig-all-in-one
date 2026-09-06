// API endpoint configuration
const API_BASE_URL = import.meta.env.DEV
  ? 'http://guineapig-ops-web.local:6880'
  : `${window.location.protocol}//${window.location.hostname}${window.location.port ? ':' + window.location.port : ''}`

const WEBSOCKET_BASE_URL = (function() {
  if (import.meta.env.DEV) {
    return 'ws://guineapig-ops-web.local:6880';
  }
  let wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  let host = window.location.host;
  return `${wsProtocol}//${host}/admin/api/v1`;
})();

// 运营管理后台 API 使用 /admin/api/v1 前缀
const ADMIN_PREFIX = `${API_BASE_URL}/admin/api/v1`

export const API_ENDPOINTS = {
  AUTH: {
    REGISTER: `${API_BASE_URL}/api/v1/client/register`,
    LOGIN: `${API_BASE_URL}/api/v1/client/login`
  },
  USERS: {
    SEARCH: `${ADMIN_PREFIX}/user/search`,
    LIST: `${ADMIN_PREFIX}/users`,
    DECRYPT_USER_INFO: `${ADMIN_PREFIX}/user/decryptUserInfo`
  },
  AIMODEL: {
    LIST: `${ADMIN_PREFIX}/aimodel/list`
  },
  FILE: {
    LIST: `${ADMIN_PREFIX}/file/list`
  },
  SKILL: {
    LIST: `${ADMIN_PREFIX}/skill/list`
  },
  MCP: {
    LIST: `${ADMIN_PREFIX}/mcp/list`
  },
  MEMORY: {
    LIST: `${ADMIN_PREFIX}/memory/list`,
    GET: `${ADMIN_PREFIX}/memory/get`,
    DELETE: `${ADMIN_PREFIX}/memory/delete`
  },
  CHAT: {
    CONVERSATION_HISTORY: `${ADMIN_PREFIX}/chat/conversation-history`,
    MESSAGES: `${ADMIN_PREFIX}/chat/messages`
  },
  OTEL: {
    LIST: `${ADMIN_PREFIX}/otel/list`,
    CHART_DATA: `${ADMIN_PREFIX}/otel/chart/data`
  },
  SCHEDULER: {
    LIST: `${ADMIN_PREFIX}/task-scheduler/list`
  },
  BOT: {
    LIST: `${ADMIN_PREFIX}/bot/list`
  }
}

export default {
  API_BASE_URL,
  WEBSOCKET_BASE_URL,
  API_ENDPOINTS
} 