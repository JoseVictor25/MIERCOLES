/**
 * useCollaboration.js
 *
 * Hook que gestiona la conexión WebSocket con el backend (Django Channels)
 * para colaboración en tiempo real en el editor de diagramas.
 *
 * Funcionalidades:
 *   - Conecta/desconecta automáticamente al montar/desmontar
 *   - Envía actualizaciones del diagrama (nodes + edges) al servidor con debounce
 *   - Envía la posición del cursor del usuario actual
 *   - Recibe actualizaciones de otros colaboradores y las aplica al estado
 *   - Muestra cursores de colaboradores en tiempo real
 *   - Expone lista de usuarios conectados en la sala
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import toast from 'react-hot-toast';
import { useChatStore } from '../store/chatStore';

// Colores asignados a colaboradores (rotación automática)
const CURSOR_COLORS = [
  '#2563eb', '#dc2626', '#16a34a', '#d97706',
  '#7c3aed', '#db2777', '#0891b2', '#65a30d',
];

export const getColorForUser = (userId) => {
  const hash = String(userId).split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return CURSOR_COLORS[hash % CURSOR_COLORS.length];
};

const getWsBase = () => {
  const envWs = import.meta.env.VITE_WS_URL;
  if (typeof window !== 'undefined') {
    const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    // Si estamos en un servidor remoto desplegado, conectar por el puerto del navegador (Nginx en 80 o 443)
    if (!isLocalhost && (!envWs || envWs.includes('localhost') || envWs.includes('127.0.0.1'))) {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${protocol}//${window.location.host}`;
    }
  }
  return envWs || (typeof window !== 'undefined'
    ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.hostname}:8000`
    : 'ws://localhost:8000');
};

const WS_BASE = getWsBase();
const DEBOUNCE_MS = 300;       // ms de espera antes de enviar actualización de diagrama
const CURSOR_THROTTLE_MS = 60; // ms mínimos entre envíos de cursor (~16 fps)
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECTS = 5;

export function useCollaboration({ diagramId, nodes, edges, onRemoteUpdate, onChatMessage, enabled = true }) {
  const wsRef       = useRef(null);
  const debounceRef = useRef(null);
  const cursorRef   = useRef(0);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const isUnmounting = useRef(false);
  const onChatMessageRef = useRef(onChatMessage);
  onChatMessageRef.current = onChatMessage;

  const [collaborators, setCollaborators] = useState({}); // { userId: { username, x, y, color, lastSeen } }
  const [wsStatus, setWsStatus]           = useState('disconnected'); // 'connecting' | 'connected' | 'disconnected'

  // Obtiene el token JWT del localStorage
  const getToken = () => localStorage.getItem('access_token') || '';

  // ── Conexión WebSocket ─────────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (!diagramId || !enabled) return;

    const token = getToken();
    if (!token) {
      console.warn('[Collab] No JWT token found; skipping WebSocket connection');
      return;
    }

    const url = `${WS_BASE}/ws/diagram/${diagramId}/?token=${encodeURIComponent(token)}`;
    setWsStatus('connecting');

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectCountRef.current = 0;
      setWsStatus('connected');
      console.info('[Collab] WebSocket connected — diagram', diagramId);
      useChatStore.getState().catchUp(diagramId);
    };

    ws.onmessage = (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }

      switch (data.type) {
        case 'chat_message':
          if (data.message) onChatMessageRef.current?.(data.message);
          break;

        case 'chat_message_update':
          if (data.message) useChatStore.getState().updateMessage(diagramId, data.message);
          break;

        case 'ai_typing':
          useChatStore.getState().setTyping(diagramId, data);
          break;

        case 'ai_settings':
          useChatStore.getState().setAISettings(diagramId, data.settings);
          break;

        case 'chat_error':
          toast.error(data.detail || 'No se pudo enviar el mensaje.');
          break;
        case 'diagram_update':
          // Otro colaborador envió el estado del diagrama
          if (typeof onRemoteUpdate === 'function') {
            onRemoteUpdate({ nodes: data.nodes, edges: data.edges });
          }
          // Actualizar lastSeen del colaborador
          setCollaborators(prev => ({
            ...prev,
            [data.user_id]: {
              ...(prev[data.user_id] || {}),
              username: data.username || prev[data.user_id]?.username,
              color: getColorForUser(data.user_id),
              lastSeen: Date.now(),
            },
          }));
          break;

        case 'cursor_move':
          setCollaborators(prev => ({
            ...prev,
            [data.user_id]: {
              ...(prev[data.user_id] || {}),
              username: data.username || prev[data.user_id]?.username,
              x: data.x,
              y: data.y,
              color: data.color || getColorForUser(data.user_id),
              lastSeen: Date.now(),
            },
          }));
          break;

        case 'user_join':
          setCollaborators(prev => {
            // Evitar notificaciones duplicadas si ya estaba en la lista (reconexiones)
            if (!prev[data.user_id]) {
              toast(`${data.username || 'Alguien'} ha entrado al diagrama`, { icon: '👋', id: `join-${data.user_id}` });
            }
            return {
              ...prev,
              [data.user_id]: {
                ...(prev[data.user_id] || {}),
                username: data.username || prev[data.user_id]?.username,
                color: getColorForUser(data.user_id),
                x: 0,
                y: 0,
                lastSeen: Date.now(),
              },
            };
          });
          break;

        case 'user_leave':
          setCollaborators(prev => {
            const next = { ...prev };
            if (next[data.user_id]) {
              toast(`${next[data.user_id].username} ha salido`, { icon: '🚪', id: `leave-${data.user_id}` });
              delete next[data.user_id];
            }
            return next;
          });
          break;

        case 'pong':
          break;

        default:
          break;
      }
    };

    ws.onerror = (err) => {
      console.error('[Collab] WebSocket error', err);
    };

    ws.onclose = (event) => {
      setWsStatus('disconnected');
      console.info('[Collab] WebSocket closed — code', event.code);

      // Reconexión automática (excepto si cerramos intencionalmente o auth falló)
      if (!isUnmounting.current && event.code !== 4001 && event.code !== 4003 && event.code !== 1000) {
        if (reconnectCountRef.current < MAX_RECONNECTS) {
          reconnectCountRef.current += 1;
          const delay = RECONNECT_DELAY_MS * reconnectCountRef.current;
          console.info(`[Collab] Reconnecting in ${delay}ms (attempt ${reconnectCountRef.current})`);
          reconnectTimerRef.current = setTimeout(connect, delay);
        }
      }
    };
  }, [diagramId, enabled, onRemoteUpdate]);

  // ── Montaje / desmontaje ───────────────────────────────────────────────────
  useEffect(() => {
    isUnmounting.current = false;
    connect();

    return () => {
      isUnmounting.current = true;
      clearTimeout(reconnectTimerRef.current);
      clearTimeout(debounceRef.current);
      if (wsRef.current) {
        wsRef.current.close(1000, 'Component unmounted');
        wsRef.current = null;
      }
    };
  }, [connect]);

  // ── Enviar actualización del diagrama (con debounce) ──────────────────────
  const sendDiagramUpdate = useCallback((nextNodes, nextEdges) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const ws = wsRef.current;
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      ws.send(JSON.stringify({
        type: 'diagram_update',
        nodes: nextNodes,
        edges: nextEdges,
        timestamp: Date.now(),
      }));
    }, DEBOUNCE_MS);
  }, []);

  // ── Enviar movimiento de cursor (throttled) ────────────────────────────────
  const sendCursorMove = useCallback((x, y, color) => {
    const now = Date.now();
    if (now - cursorRef.current < CURSOR_THROTTLE_MS) return;
    cursorRef.current = now;

    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'cursor_move', x, y, color }));
  }, []);

  const sendChatMessage = useCallback((content) => {
    const ws = wsRef.current;
    const text = typeof content === 'string' ? content.trim() : '';
    if (!ws || ws.readyState !== WebSocket.OPEN || !text || text.length > 2000) return false;
    ws.send(JSON.stringify({ type: 'chat_message', content: text }));
    return true;
  }, []);

  const sendProposalDecision = useCallback((messageId, decision) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: 'proposal_decision', message_id: messageId, decision }));
    return true;
  }, []);

  const sendProposalResult = useCallback((messageId, applied, failed) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify({ type: 'proposal_result', message_id: messageId,
      applied, failed: failed.map(item => ({ reason: item.reason })) }));
    return true;
  }, []);

  // ── Limpiar colaboradores inactivos (> 10 s sin señal) ────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setCollaborators(prev => {
        const next = {};
        for (const [id, c] of Object.entries(prev)) {
          if (now - c.lastSeen < 10_000) next[id] = c;
        }
        return next;
      });
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  return {
    wsStatus,
    collaborators,
    sendDiagramUpdate,
    sendCursorMove,
    sendChatMessage,
    sendProposalDecision,
    sendProposalResult,
  };
}
