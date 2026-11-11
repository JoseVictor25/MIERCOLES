import { useState, useEffect, useRef } from 'react';
import { X, Send, Sparkles, Bot, User, Loader2, Mic, MicOff } from 'lucide-react';
import api from '../api/axios';

/**
 * AIChatPanel — Panel de chat con IA (CU-09 y CU-04)
 * Props:
 *   isOpen          : boolean
 *   onClose         : () => void
 *   diagramData     : { nodes, edges }   — estado actual del diagrama
 *   onApplyAIUpdates: (updates) => void  — función para ejecutar comandos de la IA
 */
export default function AIChatPanel({ isOpen, onClose, diagramData, onApplyAIUpdates, topOffset = 0 }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: '¡Hola! Soy tu asistente de diseño UML. Puedo ayudarte a mejorar tu diagrama de clases.\n\n**Puedo sugerirte:**\n- Clases o atributos faltantes\n- Mejoras en las relaciones\n- Patrones de diseño adecuados\n- Buenas prácticas de OOP\n\n¿Qué necesitas?',
      model: null,
    },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => {
    // Configurar reconocimiento de voz (CU-04)
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      recognitionRef.current = new SpeechRecognition();
      recognitionRef.current.continuous = true;
      recognitionRef.current.interimResults = false;
      recognitionRef.current.lang = 'es-ES'; // O idioma preferido

      recognitionRef.current.onresult = (event) => {
        const transcript = event.results[event.results.length - 1][0].transcript;
        setInput(prev => prev ? prev + ' ' + transcript : transcript);
      };

      recognitionRef.current.onerror = (e) => {
        console.error("Speech error", e);
        setIsListening(false);
      };
      recognitionRef.current.onend = () => setIsListening(false);
    }
  }, []);

  const toggleListen = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current?.start();
        setIsListening(true);
      } catch (e) {
        setIsListening(false);
      }
    }
  };

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || loading) return;

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
    }

    const text = input.trim();
    if (!text || loading) return;

    setMessages(prev => [...prev, { role: 'user', content: text }]);
    setInput('');
    setLoading(true);

    try {
      const res = await api.post('ai/suggest/', {
        message: text,
        diagram_data: diagramData || { nodes: [], edges: [] },
      });
      const result = res.data.updates?.length && onApplyAIUpdates
        ? onApplyAIUpdates(res.data.updates)
        : { applied: [], failed: [] };
      const failures = [...(res.data.rejected || []), ...(result.failed || [])];
      const summary = result.applied?.length ? `${result.applied.length} cambios aplicados.` : '';
      const problems = failures.length ? `No se pudo: ${failures.map(item => item.reason).join('; ')}` : '';
      const noChange = res.data.updates?.length && !result.applied?.length && !failures.length
        ? 'No se aplicaron cambios.' : '';
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: [res.data.reply, summary, problems, noChange].filter(Boolean).join('\n'),
        model: res.data.model,
      }]);
    } catch (err) {
      const errMsg = ([503, 404].includes(err.response?.status)
        ? 'Inicia el servidor local de LM Studio y verifica los modelos' : null)
        || err.response?.data?.detail
        || (err.code === 'ECONNABORTED' ? 'Tiempo de espera agotado al conectar con la IA.' : null)
        || (err.response?.status === 504 ? 'Tiempo de espera agotado en el servidor (504).' : null)
        || (err.response?.status === 502 ? 'Servidor backend no disponible (502).' : null)
        || (err.message && !err.message.includes('status code') ? err.message : null)
        || 'Error al conectar con el servidor.';
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `❌ ${errMsg}`, model: null, isError: true },
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

  const QUICK_PROMPTS = [
    '¿Qué clases me faltan?',
    '¿Mejoras en relaciones?',
    '¿Qué patrón de diseño aplicar?',
    'Revisa mis atributos',
  ];

  if (!isOpen) return null;

  return (
    <>
      {/* Overlay */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(0,0,0,0.3)',
          backdropFilter: 'blur(2px)',
        }}
      />

      {/* Panel */}
      <div style={{
        position: 'fixed', right: 0, top: topOffset, bottom: 0,
        width: '400px', zIndex: 201,
        background: 'linear-gradient(180deg, #0f172a 0%, #1e293b 100%)',
        border: '1px solid rgba(99, 102, 241, 0.3)',
        borderRight: 'none',
        display: 'flex', flexDirection: 'column',
        boxShadow: '-8px 0 40px rgba(0,0,0,0.5)',
        animation: 'slideInRight 0.25s ease',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 20px',
          borderBottom: '1px solid rgba(99, 102, 241, 0.2)',
          background: 'linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(139,92,246,0.1) 100%)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div style={{
              width: 36, height: 36, borderRadius: '10px',
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 12px rgba(99,102,241,0.4)',
            }}>
              <Sparkles size={18} color="#fff" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '15px', color: '#f1f5f9' }}>
                Asistente UML IA
              </div>
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                IA local
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', padding: '4px', borderRadius: '6px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Messages */}
        <div style={{
          flex: 1, overflowY: 'auto', padding: '16px',
          display: 'flex', flexDirection: 'column', gap: '12px',
        }}>
          {messages.map((msg, i) => (
            <div key={i} style={{
              display: 'flex', gap: '10px',
              flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
              alignItems: 'flex-start',
            }}>
              {/* Avatar */}
              <div style={{
                width: 30, height: 30, borderRadius: '8px', flexShrink: 0,
                background: msg.role === 'user'
                  ? 'linear-gradient(135deg, #2563eb, #3b82f6)'
                  : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {msg.role === 'user'
                  ? <User size={14} color="#fff" />
                  : <Bot size={14} color="#fff" />
                }
              </div>

              {/* Bubble */}
              <div style={{
                maxWidth: '80%',
                background: msg.role === 'user'
                  ? 'linear-gradient(135deg, #1d4ed8, #2563eb)'
                  : msg.isError
                    ? 'rgba(239,68,68,0.12)'
                    : 'rgba(255,255,255,0.06)',
                border: msg.role === 'user'
                  ? '1px solid rgba(59,130,246,0.5)'
                  : msg.isError
                    ? '1px solid rgba(239,68,68,0.3)'
                    : '1px solid rgba(255,255,255,0.08)',
                borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                padding: '10px 14px',
              }}>
                <div style={{
                  fontSize: '13px',
                  color: msg.role === 'user' ? '#e0f2fe' : '#e2e8f0',
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                }}>
                  {msg.content}
                </div>
                {msg.model && (
                  <div style={{ fontSize: '10px', color: '#6366f1', marginTop: '6px' }}>
                    🤖 {msg.model}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <div style={{
                width: 30, height: 30, borderRadius: '8px',
                background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Bot size={14} color="#fff" />
              </div>
              <div style={{
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.08)',
                borderRadius: '14px 14px 14px 4px',
                padding: '12px 16px',
                display: 'flex', gap: '6px', alignItems: 'center',
              }}>
                <div className="typing-dot" />
                <div className="typing-dot" style={{ animationDelay: '0.2s' }} />
                <div className="typing-dot" style={{ animationDelay: '0.4s' }} />
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Quick prompts */}
        <div style={{
          padding: '8px 16px', borderTop: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', flexWrap: 'wrap', gap: '5px',
        }}>
          {QUICK_PROMPTS.map(p => (
            <button
              key={p}
              onClick={() => { setInput(p); inputRef.current?.focus(); }}
              style={{
                fontSize: '11px', padding: '4px 9px', borderRadius: '20px',
                background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)',
                color: '#a5b4fc', cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(99,102,241,0.2)'}
              onMouseLeave={e => e.currentTarget.style.background = 'rgba(99,102,241,0.1)'}
            >
              {p}
            </button>
          ))}
        </div>

        {/* Input */}
        <div style={{ padding: '12px 16px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
          <div style={{
            display: 'flex', gap: '8px', alignItems: 'flex-end',
            background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(99,102,241,0.25)',
            borderRadius: '12px', padding: '8px 12px',
            transition: 'border-color 0.15s ease',
          }}>
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Escribe tu pregunta (Enter para enviar)..."
              disabled={loading}
              style={{
                flex: 1, background: 'none', border: 'none', outline: 'none',
                color: '#f1f5f9', fontSize: '13px', resize: 'none',
                fontFamily: 'inherit', lineHeight: 1.5,
                maxHeight: '100px', overflowY: 'auto',
              }}
            />
            {/* Botón de micrófono */}
            {recognitionRef.current && (
              <button
                onClick={toggleListen}
                title="Dictar por voz"
                style={{
                  width: 32, height: 32, borderRadius: '8px', border: 'none',
                  background: isListening ? 'rgba(239, 68, 68, 0.2)' : 'rgba(99,102,241,0.1)',
                  color: isListening ? '#ef4444' : '#a5b4fc',
                  cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, transition: 'all 0.15s ease',
                }}
              >
                {isListening ? <MicOff size={16} /> : <Mic size={16} />}
              </button>
            )}
            {/* Botón de enviar */}
            <button
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              style={{
                width: 32, height: 32, borderRadius: '8px', border: 'none',
                background: loading || !input.trim()
                  ? 'rgba(99,102,241,0.2)'
                  : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                color: '#fff', cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0, transition: 'all 0.15s ease',
              }}
            >
              {loading ? <Loader2 size={14} className="spin" /> : <Send size={14} />}
            </button>
          </div>
          <div style={{ fontSize: '10px', color: '#475569', marginTop: '6px', textAlign: 'center' }}>
            Shift+Enter para nueva línea • Enter para enviar
          </div>
        </div>
      </div>

      <style>{`
        @keyframes slideInRight {
          from { transform: translateX(100%); opacity: 0; }
          to   { transform: translateX(0);    opacity: 1; }
        }
        .typing-dot {
          width: 6px; height: 6px; border-radius: 50%;
          background: #6366f1;
          animation: typingBounce 0.8s infinite ease-in-out;
        }
        @keyframes typingBounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.5; }
          40% { transform: translateY(-6px); opacity: 1; }
        }
        .spin {
          animation: spin 0.8s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </>
  );
}
