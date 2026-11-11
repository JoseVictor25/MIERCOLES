import { useState } from 'react';
import AIChatPanel from './AIChatPanel';
import ProjectChatPanel from './ProjectChatPanel';
import { useChatStore } from '../store/chatStore';
import { X } from 'lucide-react';
import './ProjectChatTabs.css';

export default function ProjectChatTabs({ isOpen, onClose, projectId, userId, canWrite, isOwner, participants,
  wsStatus, sendChatMessage, sendProposalDecision, sendProposalResult, onApplyProposal,
  diagramData, onApplyAIUpdates }) {
  const [tab, setTab] = useState('team');
  const unread = useChatStore(state => state.unreadByProject[String(projectId)] || 0);
  return <>
    <ProjectChatPanel isOpen={isOpen && tab === 'team'} onClose={onClose} projectId={projectId}
      userId={userId} canWrite={canWrite} isOwner={isOwner} participants={participants} wsStatus={wsStatus}
      sendChatMessage={sendChatMessage} sendProposalDecision={sendProposalDecision}
      sendProposalResult={sendProposalResult} onApplyProposal={onApplyProposal} />
    <AIChatPanel isOpen={isOpen && tab === 'ai'} onClose={onClose} diagramData={diagramData}
      onApplyAIUpdates={onApplyAIUpdates} topOffset={42} />
    {isOpen && <nav className="project-chat-tabs" aria-label="Pestañas del chat">
      <button onClick={() => setTab('team')} className={tab === 'team' ? 'active' : ''} aria-selected={tab === 'team'}>
        Equipo {unread > 0 ? `(${unread})` : ''}
      </button>
      <button onClick={() => setTab('ai')} className={tab === 'ai' ? 'active' : ''} aria-selected={tab === 'ai'}>
        Asistente IA
      </button>
      <button onClick={onClose} aria-label="Cerrar chat" className="project-chat-tabs-close"><X size={17} /></button>
    </nav>}
  </>;
}
