import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { getColorForUser } from '../hooks/useCollaboration';
import { useChatStore } from '../store/chatStore';
import toast from 'react-hot-toast';
import { Bot, Check, ChevronUp, Clock3, Send, Settings2, X } from 'lucide-react';
import './ProjectChatPanel.css';

const EMPTY_MESSAGES = [];
const PROPOSAL_STATUS = {
  pending: 'Pendiente', approved: 'Aprobada', rejected: 'Rechazada',
  applied: 'Aplicada', partial: 'Aplicada parcialmente', failed: 'Fallida',
};
const ACTION_NAMES = {
  add_class: 'Agregar clase', delete_class: 'Eliminar clase', rename_class: 'Renombrar clase',
  add_attribute: 'Agregar atributo', delete_attribute: 'Eliminar atributo',
  add_relation: 'Agregar relación', delete_relation: 'Eliminar relación',
  update_relation_type: 'Cambiar tipo de relación', set_multiplicity: 'Fijar multiplicidades',
};

export function describeAIUpdate(update) {
  const label = ACTION_NAMES[update.action] || 'Cambio';
  if (update.action === 'rename_class') return `${label}: ${update.name} → ${update.new_name}`;
  if (update.class_name) return `${label}: ${update.class_name}.${update.attr_name}`;
  if (update.source_class) {
    const pair = `${update.source_class} ↔ ${update.target_class}`;
    if (update.action === 'set_multiplicity') {
      return `${label}: ${pair} (${update.source_class}: ${update.source_multiplicity}, ${update.target_class}: ${update.target_multiplicity})`;
    }
    return `${label}: ${pair}${update.relation_type ? ` → ${update.relation_type}` : ''}`;
  }
  return `${label}: ${update.name || ''}`;
}

function proposalStatusText(message, participants) {
  const meta = message.meta || {};
  const requester = message.reply_to_username || participants[message.reply_to_user_id] || 'Alguien';
  const decider = participants[meta.decided_by] || (meta.decided_by === message.reply_to_user_id ? requester : 'Alguien');
  if (meta.status === 'pending') return `Pendiente de ${requester}`;
  if (meta.status === 'rejected') return `Rechazado por ${decider}`;
  if (meta.status === 'approved') return `Aprobado por ${decider} · esperando aplicación`;
  if (['applied', 'partial', 'failed'].includes(meta.status)) {
    const count = meta.result?.applied || 0;
    return `Aprobado por ${decider}: ${count} cambio${count === 1 ? '' : 's'} aplicado${count === 1 ? '' : 's'}`;
  }
  return PROPOSAL_STATUS[meta.status] || 'Propuesta';
}

export default function ProjectChatPanel({ isOpen, onClose, projectId, userId, canWrite, isOwner,
  participants = {}, wsStatus, sendChatMessage, sendProposalDecision, sendProposalResult, onApplyProposal }) {
  const [draft, setDraft] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const listRef = useRef(null);
  const textareaRef = useRef(null);
  const wasAtBottom = useRef(true);
  const previousHeight = useRef(null);
  const approvals = useRef(new Set());
  const localResults = useRef(new Map());
  const applying = useRef(new Set());
  const previousWsStatus = useRef(wsStatus);
  const messages = useChatStore(state => state.messagesByProject[String(projectId)] || EMPTY_MESSAGES);
  const hasMore = useChatStore(state => state.hasMoreByProject[String(projectId)]);
  const error = useChatStore(state => state.errorByProject[String(projectId)]);
  const loadOlder = useChatStore(state => state.loadOlder);
  const setActive = useChatStore(state => state.setActive);
  const aiSettings = useChatStore(state => state.aiSettingsByProject[String(projectId)]);
  const typing = useChatStore(state => state.typingByProject[String(projectId)]);
  const loadAISettings = useChatStore(state => state.loadAISettings);
  const patchAISettings = useChatStore(state => state.patchAISettings);

  useEffect(() => {
    if (projectId) loadAISettings(projectId).catch(() => toast.error('No se pudo cargar la configuración de IA.'));
  }, [projectId, loadAISettings]);

  const applyApproved = async (message) => {
    if (localResults.current.has(message.id) || applying.current.has(message.id)) return;
    applying.current.add(message.id);
    let result;
    try {
      result = await onApplyProposal(message.meta.updates || []);
    } catch {
      result = { applied: [], failed: (message.meta.updates || []).map(update => ({ update, reason: 'Error al aplicar el cambio.' })) };
    }
    const report = { applied: result?.applied?.length || 0, failed: result?.failed || [] };
    localResults.current.set(message.id, report);
    applying.current.delete(message.id);
    sendProposalResult(message.id, report.applied, report.failed);
  };

  useEffect(() => {
    for (const message of messages) {
      if (approvals.current.has(message.id) && message.meta?.status === 'approved'
          && message.meta?.decided_by === userId) {
        approvals.current.delete(message.id);
        applyApproved(message);
      }
    }
    if (wsStatus === 'connected' && previousWsStatus.current !== 'connected') {
      for (const [id, report] of localResults.current) {
        sendProposalResult(id, report.applied, report.failed);
      }
    }
    previousWsStatus.current = wsStatus;
    for (const message of messages) {
      if (['applied', 'partial', 'failed', 'rejected'].includes(message.meta?.status)) {
        localResults.current.delete(message.id);
      }
    }
  }, [messages, userId, wsStatus]);

  useEffect(() => {
    if (isOpen) setActive(projectId, true);
    return () => { if (isOpen) setActive(projectId, false); };
  }, [isOpen, projectId, setActive]);

  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list || !isOpen) return;
    if (previousHeight.current !== null) {
      list.scrollTop += list.scrollHeight - previousHeight.current;
      previousHeight.current = null;
    } else if (wasAtBottom.current) {
      list.scrollTop = list.scrollHeight;
    }
  }, [messages, isOpen]);

  const send = () => {
    if (!canWrite || !draft.trim()) return;
    if (sendChatMessage(draft)) {
      wasAtBottom.current = true;
      setDraft('');
      if (textareaRef.current) textareaRef.current.style.height = 'auto';
    }
  };
  const handleDraft = (value) => {
    setDraft(value);
    const input = textareaRef.current;
    if (input) {
      input.style.height = 'auto';
      input.style.height = `${Math.min(input.scrollHeight, 110)}px`;
    }
  };
  const mention = () => {
    handleDraft(draft.replace(/(^|\s)@$/, '$1') + `${draft && !draft.endsWith(' ') && !draft.endsWith('@') ? ' ' : ''}@ia `);
    textareaRef.current?.focus();
  };
  const decide = (message, decision) => {
    if (sendProposalDecision(message.id, decision)) {
      if (decision === 'approve') approvals.current.add(message.id);
    } else toast.error('El chat está desconectado.');
  };
  const changeSettings = async (patch) => {
    try { await patchAISettings(projectId, patch); }
    catch (error) { toast.error(error.response?.data?.detail || 'No se pudo guardar la configuración.'); }
  };
  const older = async () => {
    previousHeight.current = listRef.current?.scrollHeight ?? null;
    const count = useChatStore.getState().messagesByProject[String(projectId)]?.length || 0;
    await loadOlder(projectId);
    if ((useChatStore.getState().messagesByProject[String(projectId)]?.length || 0) === count) {
      previousHeight.current = null;
    }
  };
  if (!isOpen) return null;

  return <>
    <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,.3)' }} />
    <section className="project-chat-panel">
      <header className="project-chat-header">
        <div>
          <strong>Chat del proyecto</strong>
          <span className="project-chat-subtitle">Conversación del equipo</span>
        </div>
        <div className="project-chat-header-actions">
          <span className={`project-chat-connection ${wsStatus}`} title={wsStatus === 'connected' ? 'Conectado' : wsStatus === 'connecting' ? 'Conectando' : 'Sin conexión'}>
            <span className="project-chat-dot" />
            {wsStatus === 'connected' ? 'En línea' : wsStatus === 'connecting' ? 'Conectando' : 'Sin conexión'}
          </span>
          {isOwner && <button className="project-chat-icon-button" onClick={() => setSettingsOpen(value => !value)}
            title="Configurar asistente IA" aria-label="Configurar asistente IA"><Settings2 size={17} /></button>}
        </div>
      </header>
      {!isOwner && aiSettings && <div className="project-chat-mode-badge" title="Configura la IA el dueño del proyecto">
        <Bot size={13} /> {aiSettings.enabled ? (aiSettings.mode === 'advisor' ? 'IA · Solo aconseja' : 'IA · Puede proponer') : 'IA desactivada'}
      </div>}
      {isOwner && settingsOpen && aiSettings && <div className="project-chat-settings">
        <div className="project-chat-settings-title"><strong>Asistente del equipo</strong>
          <button className="project-chat-icon-button" onClick={() => setSettingsOpen(false)} aria-label="Cerrar configuración"><X size={16} /></button>
        </div>
        <label className="project-chat-toggle-row"><span>IA activa</span>
          <input type="checkbox" checked={aiSettings.enabled} onChange={e => changeSettings({ enabled: e.target.checked })} />
        </label>
        <label>Modo<select value={aiSettings.mode} onChange={e => changeSettings({ mode: e.target.value })}>
          <option value="advisor">Solo aconseja</option><option value="proposer">Puede proponer cambios al lienzo</option>
        </select></label>
        <label>Rol de la IA<select value={aiSettings.persona} onChange={e => changeSettings({ persona: e.target.value })}>
          <option value="moderator">Moderador</option><option value="senior_dev">Desarrollador senior</option>
        </select></label>
      </div>}
      <div className="project-chat-list" ref={listRef} onScroll={event => {
        const el = event.currentTarget;
        wasAtBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      }}>
        {hasMore && <button className="project-chat-older" onClick={older}><ChevronUp size={14} /> Cargar anteriores</button>}
        {error && <p role="alert" style={{ color: '#fca5a5' }}>{error}</p>}
        {!messages.length && <div className="project-chat-empty"><span className="project-chat-empty-icon">✦</span>
          <strong>Empieza la conversación</strong><span>Comparte una idea con tu equipo o escribe @ia para consultar al asistente.</span>
        </div>}
        {messages.map((message, index) => {
          const own = message.author_id === userId;
          const color = getColorForUser(message.author_id || 'ia');
          const name = message.is_ai ? 'Asistente IA' : message.username || participants[message.author_id] || 'Alguien';
          const date = new Date(message.created_at);
          const day = date.toDateString();
          const previousDay = index ? new Date(messages[index - 1].created_at).toDateString() : null;
          const forMe = message.is_ai && message.reply_to_user_id === userId;
          if (message.kind === 'error' || message.meta?.error) {
            return <div key={message.id}>
              {day !== previousDay && <div className="project-chat-day"><span>{date.toLocaleDateString('es-BO', { day: 'numeric', month: 'long', year: 'numeric' })}</span></div>}
              <div className="project-chat-system-notice" role="status">
                <span>IA · aviso para @{message.reply_to_username || participants[message.reply_to_user_id] || 'Alguien'}</span>
                {message.content}
              </div>
            </div>;
          }
          return <div key={message.id}>
            {day !== previousDay && <div className="project-chat-day"><span>{date.toLocaleDateString('es-BO', { day: 'numeric', month: 'long', year: 'numeric' })}</span></div>}
            <div className={`project-chat-message ${own ? 'own' : ''} ${message.is_ai ? 'ai' : ''} ${forMe ? 'for-me' : ''}`}>
              {!own && <div className="project-chat-avatar" style={{ background: message.is_ai ? '#4f46e5' : color }}>
                {message.is_ai ? <Bot size={15} /> : name[0]?.toUpperCase()}
              </div>}
              <div className="project-chat-bubble">
                <div className="project-chat-byline"><strong style={{ color: message.is_ai ? '#c7d2fe' : own ? '#dbeafe' : color }}>{name}</strong>
                  {message.is_ai && <span className="project-chat-ai-badge">IA</span>}
                  <time dateTime={message.created_at}>{date.toLocaleTimeString('es-BO', { hour: '2-digit', minute: '2-digit' })}</time>
                </div>
                {message.is_ai && message.reply_to_user_id && <div className={`project-chat-recipient ${forMe ? 'mine' : ''}`}>
                  para @{message.reply_to_username || participants[message.reply_to_user_id] || 'Alguien'}
                </div>}
                <div className="project-chat-content">{message.content}</div>
              {message.kind === 'proposal' && <div className="project-chat-proposal">
                <div className="project-chat-proposal-heading"><Check size={14} /><strong>Propuesta</strong>
                  <span>{PROPOSAL_STATUS[message.meta?.status] || 'Pendiente'}</span></div>
                <ul>{(message.meta?.updates || []).map((update, updateIndex) =>
                  <li key={updateIndex}>{describeAIUpdate(update)}</li>)}</ul>
                <div className="project-chat-proposal-status">{proposalStatusText(message, participants)}</div>
                {message.meta?.status === 'pending' && message.reply_to_user_id === userId && canWrite && <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <button className="project-chat-approve" onClick={() => decide(message, 'approve')}>Aprobar</button>
                  <button className="project-chat-reject" onClick={() => decide(message, 'reject')}>Rechazar</button>
                </div>}
                {!!message.meta?.result?.failed?.length && <div className="project-chat-failures">
                  <strong>No aplicados:</strong>
                  <ul>{message.meta.result.failed.map((item, failedIndex) => <li key={failedIndex}>{item.reason}</li>)}</ul>
                </div>}
              </div>}
              </div>
            </div>
          </div>;
        })}
        {typing && Object.keys(typing).length > 0 && <div className="project-chat-typing">
          <span className="project-chat-typing-dots">•••</span> El asistente está respondiendo a {Object.values(typing).join(', ')}…
        </div>}
      </div>
      <div className="project-chat-footer">
        {!canWrite ? <div className="project-chat-readonly"><Clock3 size={16} /> Solo lectura · puedes seguir la conversación del equipo</div> : <>
          {aiSettings?.enabled && /(^|\s)@$/.test(draft) && <button className="project-chat-mention" onClick={mention}>
            <Bot size={15} /> @ia <span>Consultar al asistente</span>
          </button>}
          <div className="project-chat-composer">
            <textarea ref={textareaRef} rows={1} value={draft} maxLength={2000}
              onChange={event => handleDraft(event.target.value)} disabled={wsStatus !== 'connected'}
              placeholder={wsStatus === 'connected' ? 'Escribe un mensaje…' : 'Esperando conexión…'}
              onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); send(); } }} />
            <button className="project-chat-send" onClick={send} aria-label="Enviar mensaje"
              disabled={wsStatus !== 'connected' || !draft.trim()}><Send size={17} /></button>
          </div>
          <div className="project-chat-hint"><span>Enter envía · Shift+Enter salto de línea · @ia para consultar a la IA</span>
            {draft.length >= 1700 && <span className="project-chat-counter">{draft.length}/2000</span>}
          </div>
        </>}
      </div>
    </section>
  </>;
}
