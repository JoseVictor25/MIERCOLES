import { create } from 'zustand';
import api from '../api/axios';

const merge = (oldMessages, incoming) => {
  const byId = new Map(oldMessages.map(message => [message.id, message]));
  incoming.forEach(message => byId.set(message.id, message));
  return [...byId.values()].sort((a, b) => a.id - b.id);
};

export const useChatStore = create((set, get) => ({
  messagesByProject: {},
  hasMoreByProject: {},
  unreadByProject: {},
  activeProjectId: null,
  errorByProject: {},
  aiSettingsByProject: {},
  typingByProject: {},

  setActive: (projectId, active) => set(state => ({
    activeProjectId: active ? String(projectId) : null,
    unreadByProject: active ? { ...state.unreadByProject, [projectId]: 0 } : state.unreadByProject,
  })),

  appendMessage: (projectId, message) => set(state => {
    const key = String(projectId);
    const old = state.messagesByProject[key] || [];
    if (old.some(item => item.id === message.id)) return state;
    return {
      messagesByProject: { ...state.messagesByProject, [key]: merge(old, [message]) },
      unreadByProject: { ...state.unreadByProject,
        [key]: state.activeProjectId === key ? 0 : (state.unreadByProject[key] || 0) + 1 },
    };
  }),

  updateMessage: (projectId, message) => set(state => {
    const key = String(projectId);
    return { messagesByProject: {
      ...state.messagesByProject,
      [key]: merge(state.messagesByProject[key] || [], [message]),
    } };
  }),

  setTyping: (projectId, event) => set(state => {
    const key = String(projectId);
    const typing = { ...(state.typingByProject[key] || {}) };
    if (event.active) typing[event.for_user_id] = event.for_username;
    else delete typing[event.for_user_id];
    return { typingByProject: { ...state.typingByProject, [key]: typing } };
  }),

  setAISettings: (projectId, settings) => set(state => ({
    aiSettingsByProject: { ...state.aiSettingsByProject, [String(projectId)]: settings },
  })),

  loadAISettings: async (projectId) => {
    const { data } = await api.get(`projects/${projectId}/ai-settings/`);
    get().setAISettings(projectId, data);
    return data;
  },

  patchAISettings: async (projectId, patch) => {
    const { data } = await api.patch(`projects/${projectId}/ai-settings/`, patch);
    get().setAISettings(projectId, data);
    return data;
  },

  loadHistory: async (projectId) => {
    const key = String(projectId);
    try {
      const { data } = await api.get(`projects/${key}/chat/`, { params: { limit: 50 } });
      set(state => ({
        messagesByProject: { ...state.messagesByProject, [key]: merge(state.messagesByProject[key] || [], data.messages) },
        hasMoreByProject: { ...state.hasMoreByProject, [key]: data.has_more },
        errorByProject: { ...state.errorByProject, [key]: null },
      }));
    } catch (error) {
      set(state => ({ errorByProject: { ...state.errorByProject, [key]: error.response?.data?.detail || 'No se pudo cargar el chat.' } }));
    }
  },

  loadOlder: async (projectId) => {
    const key = String(projectId);
    const first = get().messagesByProject[key]?.[0];
    if (!first) return;
    try {
      const { data } = await api.get(`projects/${key}/chat/`, { params: { limit: 50, before: first.id } });
      set(state => ({
        messagesByProject: { ...state.messagesByProject, [key]: merge(state.messagesByProject[key] || [], data.messages) },
        hasMoreByProject: { ...state.hasMoreByProject, [key]: data.has_more },
      }));
    } catch (error) {
      set(state => ({ errorByProject: { ...state.errorByProject, [key]: error.response?.data?.detail || 'No se pudo cargar el historial.' } }));
    }
  },

  catchUp: async (projectId) => {
    const key = String(projectId);
    const known = get().messagesByProject[key] || [];
    if (!known.length) return get().loadHistory(key);
    let lastId = known[known.length - 1].id;
    try {
      let more;
      do {
        const { data } = await api.get(`projects/${key}/chat/`, { params: { limit: 100, after: lastId } });
        data.messages.forEach(message => get().appendMessage(key, message));
        if (data.messages.length) lastId = data.messages[data.messages.length - 1].id;
        more = data.has_more && data.messages.length > 0;
      } while (more);
      // También refresca estados de propuestas recientes que conservan el mismo id.
      await get().loadHistory(key);
    } catch (error) {
      set(state => ({ errorByProject: { ...state.errorByProject, [key]: 'No se pudieron recuperar los mensajes recientes.' } }));
    }
  },
}));
