import { useState, useRef, useEffect } from 'react';
import { X, Send, Bot, User, Loader2, ChevronDown, HelpCircle } from 'lucide-react';
import api from '../api/axios';

const QUICK_QUESTIONS = [
  { icon: '🚀', text: '¿Cómo creo mi primer diagrama?' },
  { icon: '🔗', text: '¿Cómo conecto dos clases?' },
  { icon: '⚙️', text: '¿Cómo genero y ejecuto el backend?' },
  { icon: '🗄️', text: '¿Cómo configuro PostgreSQL?' },
  { icon: '📦', text: '¿Cómo exporto a Enterprise Architect?' },
];

const WELCOME_MSG = {
  role: 'assistant',
  content: '¡Hola! 👋 Soy tu guía de UMLCraft.\n\nPuedo enseñarte a usar todas las funciones: crear diagramas, conectar relaciones, generar y ejecutar el backend Spring Boot, configurar PostgreSQL y mucho más.\n\n¿En qué te puedo ayudar?',
};

function renderText(text) {
  return text.split('\n').map((line, i, arr) => (
    <span key={i}>
      {line.split(/(\*\*[^*]+\*\*)/).map((part, j) =>
        part.startsWith('**') && part.endsWith('**') ? (
          <strong key={j} style={{ color: '#93c5fd' }}>{part.slice(2, -2)}</strong>
        ) : part
      )}
      {i < arr.length - 1 && <br />}
    </span>
  ));
}

export default function HelpChatBot() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([WELCOME_MSG]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [hasUnread, setHasUnread] = useState(true);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setHasUnread(false);
      setTimeout(() => inputRef.current?.focus(), 150);
    }
  }, [isOpen]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const sendMessage = async (text) => {
    const msg = text || input.trim();
    if (!msg || loading) return;
    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: msg }]);
    setLoading(true);
    try {
      const res = await api.post('ai/help/', { message: msg });
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: res.data.reply, model: res.data.model },
      ]);
    } catch (err) {
      const errMsg = ([503, 404].includes(err.response?.status)
        ? 'Inicia el servidor local de LM Studio y verifica los modelos' : null)
        || err.response?.data?.detail
        || (err.code === 'ECONNABORTED' ? 'Tiempo de espera agotado al conectar con la IA.' : null)
        || (err.response?.status === 504 ? 'Tiempo de espera agotado en el servidor (504).' : null)
        || (err.response?.status === 502 ? 'Servidor backend no disponible (502).' : null)
        || (err.message && !err.message.includes('status code') ? err.message : null)
        || 'Error al conectar con el servidor.';
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `❌ ${errMsg}`, isError: true },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const userMsgCount = messages.filter((m) => m.role === 'user').length;

  return (
    <>
      <style>{`
        @keyframes helpSlideUp {
          from { transform: translateY(30px) scale(0.95); opacity: 0; }
          to   { transform: translateY(0) scale(1); opacity: 1; }
        }
        @keyframes helpPulse {
          0%, 100% { box-shadow: 0 8px 24px rgba(99,102,241,0.45), 0 0 0 0 rgba(99,102,241,0.5); }
          50%       { box-shadow: 0 8px 24px rgba(99,102,241,0.45), 0 0 0 10px rgba(99,102,241,0); }
        }
        @keyframes helpDot {
          0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
          40%            { transform: scale(1);   opacity: 1; }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .help-typing-dot { animation: helpDot 1.2s infinite; }
        .help-typing-dot:nth-child(2) { animation-delay: 0.2s; }
        .help-typing-dot:nth-child(3) { animation-delay: 0.4s; }
        .help-window { animation: helpSlideUp 0.3s cubic-bezier(0.34,1.56,0.64,1); }
        .help-btn-pulse { animation: helpPulse 2.5s ease-in-out infinite; }
        .help-msg-area::-webkit-scrollbar { width: 4px; }
        .help-msg-area::-webkit-scrollbar-track { background: transparent; }
        .help-msg-area::-webkit-scrollbar-thumb { background: rgba(99,102,241,0.3); border-radius: 4px; }
        .help-quick-btn:hover { background: rgba(79,70,229,0.28) !important; color: #c7d2fe !important; }
      `}</style>

      {/* ── Floating Button ── */}
      <button
        id="help-chatbot-trigger"
        onClick={() => setIsOpen((o) => !o)}
        title="Ayuda — ¿Cómo usar UMLCraft?"
        className={isOpen ? '' : 'help-btn-pulse'}
        style={{
          position: 'fixed',
          bottom: 24,
          left: 24,
          width: 56,
          height: 56,
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          transition: 'transform 0.2s ease',
        }}
        onMouseEnter={(e) => (e.currentTarget.style.transform = 'scale(1.1)')}
        onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
      >
        {isOpen ? <ChevronDown size={22} color="#fff" /> : <HelpCircle size={24} color="#fff" />}
        {hasUnread && !isOpen && (
          <span style={{
            position: 'absolute', top: 2, right: 2,
            width: 14, height: 14, borderRadius: '50%',
            background: '#f43f5e', border: '2px solid #1e1b4b',
          }} />
        )}
      </button>

      {/* ── Chat Window ── */}
      {isOpen && (
        <div
          className="help-window"
          style={{
            position: 'fixed',
            bottom: 90,
            left: 24,
            width: 380,
            height: 560,
            maxHeight: 'calc(100vh - 110px)',
            borderRadius: 20,
            background: 'linear-gradient(160deg, #0f0c29 0%, #1a1a3e 50%, #0f0c29 100%)',
            border: '1px solid rgba(99,102,241,0.35)',
            boxShadow: '0 32px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 9998,
            overflow: 'hidden',
          }}
        >
          {/* Header */}
          <div style={{
            padding: '14px 18px',
            background: 'linear-gradient(90deg, rgba(79,70,229,0.35) 0%, rgba(124,58,237,0.2) 100%)',
            borderBottom: '1px solid rgba(99,102,241,0.2)',
            display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0,
          }}>
            <div style={{
              width: 38, height: 38, borderRadius: 12,
              background: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(99,102,241,0.5)', flexShrink: 0,
            }}>
              <HelpCircle size={20} color="#fff" />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 700, fontSize: 14, color: '#f1f5f9' }}>Guía de UMLCraft</div>
              <div style={{ fontSize: 11, color: '#818cf8', marginTop: 1 }}>Asistente de ayuda · IA local</div>
            </div>
            <button
              onClick={() => setIsOpen(false)}
              style={{
                background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8, cursor: 'pointer', color: '#94a3b8',
                width: 28, height: 28, display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              <X size={15} />
            </button>
          </div>

          {/* Messages */}
          <div
            className="help-msg-area"
            style={{
              flex: 1, overflowY: 'auto', padding: '14px 14px 8px',
              display: 'flex', flexDirection: 'column', gap: 10,
            }}
          >
            {messages.map((msg, i) => (
              <div key={i} style={{
                display: 'flex',
                flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                gap: 8, alignItems: 'flex-end',
              }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 8, flexShrink: 0,
                  background: msg.role === 'user'
                    ? 'linear-gradient(135deg, #2563eb, #3b82f6)'
                    : 'linear-gradient(135deg, #4f46e5, #7c3aed)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {msg.role === 'user' ? <User size={13} color="#fff" /> : <Bot size={13} color="#fff" />}
                </div>
                <div style={{
                  maxWidth: '78%',
                  padding: '10px 13px',
                  borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                  background: msg.role === 'user'
                    ? 'linear-gradient(135deg, #1d4ed8, #2563eb)'
                    : msg.isError ? 'rgba(239,68,68,0.12)' : 'rgba(255,255,255,0.06)',
                  border: msg.role === 'user'
                    ? '1px solid rgba(59,130,246,0.5)'
                    : msg.isError ? '1px solid rgba(239,68,68,0.25)' : '1px solid rgba(255,255,255,0.07)',
                  boxShadow: msg.role === 'user' ? '0 4px 12px rgba(29,78,216,0.3)' : '0 2px 8px rgba(0,0,0,0.2)',
                }}>
                  <div style={{ fontSize: 12.5, color: msg.role === 'user' ? '#e0f2fe' : '#e2e8f0', lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>
                    {renderText(msg.content)}
                  </div>
                  {msg.model && (
                    <div style={{ fontSize: 10, color: '#6366f1', marginTop: 5 }}>🤖 {msg.model}</div>
                  )}
                </div>
              </div>
            ))}

            {/* Typing dots */}
            {loading && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end' }}>
                <div style={{
                  width: 28, height: 28, borderRadius: 8,
                  background: 'linear-gradient(135deg, #4f46e5, #7c3aed)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>
                  <Bot size={13} color="#fff" />
                </div>
                <div style={{
                  padding: '10px 16px', background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.07)', borderRadius: '14px 14px 14px 4px',
                  display: 'flex', gap: 5, alignItems: 'center',
                }}>
                  {[0, 1, 2].map((k) => (
                    <span key={k} className="help-typing-dot" style={{
                      width: 7, height: 7, borderRadius: '50%', background: '#818cf8', display: 'inline-block',
                    }} />
                  ))}
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Quick questions — shown only before first user message */}
          {userMsgCount === 0 && (
            <div style={{ padding: '0 12px 10px', display: 'flex', flexWrap: 'wrap', gap: 6, flexShrink: 0 }}>
              {QUICK_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  className="help-quick-btn"
                  onClick={() => sendMessage(q.text)}
                  disabled={loading}
                  style={{
                    background: 'rgba(79,70,229,0.12)',
                    border: '1px solid rgba(99,102,241,0.3)',
                    borderRadius: 20, color: '#a5b4fc',
                    fontSize: 11, padding: '5px 11px',
                    cursor: loading ? 'not-allowed' : 'pointer',
                    opacity: loading ? 0.5 : 1,
                    transition: 'all 0.15s ease',
                  }}
                >
                  {q.icon} {q.text}
                </button>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{
            padding: '10px 12px 14px',
            borderTop: '1px solid rgba(99,102,241,0.15)',
            display: 'flex', gap: 8,
            background: 'rgba(15,12,41,0.6)', flexShrink: 0,
          }}>
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Escribe tu pregunta sobre UMLCraft..."
              rows={1}
              style={{
                flex: 1, background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(99,102,241,0.25)', borderRadius: 12,
                color: '#e2e8f0', fontSize: 12.5, padding: '9px 12px',
                resize: 'none', outline: 'none', fontFamily: 'inherit',
                lineHeight: 1.5, minHeight: 38, maxHeight: 90, overflowY: 'auto',
                transition: 'border-color 0.15s',
              }}
              onFocus={(e) => (e.target.style.borderColor = 'rgba(99,102,241,0.6)')}
              onBlur={(e) => (e.target.style.borderColor = 'rgba(99,102,241,0.25)')}
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || loading}
              style={{
                width: 38, height: 38, borderRadius: 12, border: 'none',
                background: input.trim() && !loading
                  ? 'linear-gradient(135deg, #4f46e5, #7c3aed)'
                  : 'rgba(255,255,255,0.07)',
                cursor: input.trim() && !loading ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0, transition: 'all 0.15s ease',
                boxShadow: input.trim() && !loading ? '0 4px 12px rgba(99,102,241,0.4)' : 'none',
              }}
            >
              {loading
                ? <Loader2 size={16} color="#818cf8" style={{ animation: 'spin 1s linear infinite' }} />
                : <Send size={16} color={input.trim() ? '#fff' : '#475569'} />
              }
            </button>
          </div>
        </div>
      )}
    </>
  );
}
