import { useState, useRef, useCallback } from 'react';
import { X, Upload, ImagePlus, Loader2, Sparkles, Check, AlertCircle, Stethoscope } from 'lucide-react';
import api from '../api/axios';
import toast from 'react-hot-toast';

/**
 * ImageToUMLModal — CU-10: Generar diagrama de clases desde una imagen
 * Props:
 *   isOpen    : boolean
 *   onClose   : () => void
 *   onApply   : (nodes, edges) => void
 */
export default function ImageToUMLModal({ isOpen, onClose, onApply }) {
  const [dragging, setDragging]        = useState(false);
  const [imageFile, setImageFile]      = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [loading, setLoading]          = useState(false);
  const [result, setResult]            = useState(null);
  const [diagnosing, setDiagnosing]    = useState(false);
  const [diagnoseResult, setDiagnoseResult] = useState(null);
  const fileInputRef = useRef(null);

  const resetState = () => {
    setImageFile(null);
    setImagePreview(null);
    setResult(null);
    setLoading(false);
    setDiagnoseResult(null);
  };

  const handleClose = () => { resetState(); onClose(); };

  const processFile = (file) => {
    if (!file) return;
    const allowed = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp', 'image/gif'];
    if (!allowed.includes(file.type)) { toast.error('Usa PNG, JPG, WEBP o GIF.'); return; }
    if (file.size > 8 * 1024 * 1024) { toast.error('Máximo 8 MB.'); return; }
    setImageFile(file);
    setResult(null);
    const reader = new FileReader();
    reader.onload = (e) => setImagePreview(e.target.result);
    reader.readAsDataURL(file);
  };

  const handleDrop = useCallback((e) => {
    e.preventDefault(); setDragging(false);
    processFile(e.dataTransfer.files[0]);
  }, []);

  const handleAnalyze = async () => {
    if (!imageFile) return;
    setLoading(true); setResult(null); setDiagnoseResult(null);
    try {
      const formData = new FormData();
      formData.append('image', imageFile);
      const res = await api.post('ai/vision/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 620000,
      });
      setResult(res.data);
    } catch (err) {
      toast.error([503, 404].includes(err.response?.status)
        ? 'Inicia el servidor local de LM Studio y verifica los modelos'
        : (err.response?.data?.detail || 'Error al analizar la imagen.'));
    } finally {
      setLoading(false);
    }
  };

  const handleDiagnose = async () => {
    setDiagnosing(true);
    try {
      const res = await api.get('ai/diagnose/');
      setDiagnoseResult(res.data);
    } catch (err) {
      toast.error('Error al diagnosticar: ' + (err.response?.data?.detail || err.message));
    } finally {
      setDiagnosing(false);
    }
  };

  const handleApply = () => {
    if (!result?.nodes?.length) return;
    onApply(result.nodes, result.edges || []);
    toast.success(`${result.nodes.length} clase(s) importadas al canvas`, { icon: '🎯', duration: 3000 });
    handleClose();
  };

  if (!isOpen) return null;

  const hasError   = !!result?.error;
  const hasClasses = result?.nodes?.length > 0;

  return (
    <>
      <div onClick={handleClose} style={{
        position: 'fixed', inset: 0, zIndex: 200,
        background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(6px)',
      }} />

      <div style={{
        position: 'fixed', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '620px', maxHeight: '88vh', zIndex: 201,
        background: 'linear-gradient(160deg, #0f172a 0%, #1e293b 100%)',
        border: '1px solid rgba(139,92,246,0.3)', borderRadius: '20px',
        boxShadow: '0 30px 100px rgba(0,0,0,0.7), 0 0 60px rgba(139,92,246,0.1)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
        animation: 'modalIn 0.25s cubic-bezier(0.34,1.56,0.64,1)',
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px', borderBottom: '1px solid rgba(255,255,255,0.06)',
          background: 'linear-gradient(135deg, rgba(139,92,246,0.12), rgba(99,102,241,0.08))',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={{
              width: 42, height: 42, borderRadius: '12px',
              background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 16px rgba(139,92,246,0.4)',
            }}>
              <ImagePlus size={20} color="#fff" />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '17px', color: '#f1f5f9' }}>Imagen → Diagrama UML</div>
              <div style={{ fontSize: '12px', color: '#64748b', marginTop: '2px' }}>
                Sube una foto de un diagrama, pizarra o código y la IA lo convierte
              </div>
            </div>
          </div>
          <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b', padding: '4px' }}>
            <X size={20} />
          </button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
          {!imagePreview ? (
            /* Drop zone */
            <div
              onDrop={handleDrop}
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: `2px dashed ${dragging ? '#8b5cf6' : 'rgba(139,92,246,0.3)'}`,
                borderRadius: '16px', padding: '48px 24px', textAlign: 'center', cursor: 'pointer',
                background: dragging ? 'rgba(139,92,246,0.08)' : 'rgba(255,255,255,0.02)',
                transition: 'all 0.2s ease', userSelect: 'none',
              }}
            >
              <div style={{
                width: 64, height: 64, borderRadius: '16px',
                background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.25)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                margin: '0 auto 16px',
              }}>
                <Upload size={28} color="#8b5cf6" />
              </div>
              <div style={{ fontSize: '15px', fontWeight: 600, color: '#e2e8f0', marginBottom: '8px' }}>
                Arrastra una imagen aquí
              </div>
              <div style={{ fontSize: '13px', color: '#64748b', marginBottom: '16px' }}>
                o haz clic para seleccionarla
              </div>
              <div style={{ display: 'flex', gap: '6px', justifyContent: 'center', flexWrap: 'wrap' }}>
                {['PNG', 'JPG', 'WEBP', 'GIF'].map(f => (
                  <span key={f} style={{
                    padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
                    background: 'rgba(139,92,246,0.1)', border: '1px solid rgba(139,92,246,0.2)', color: '#a78bfa',
                  }}>{f}</span>
                ))}
              </div>
              <div style={{ fontSize: '11px', color: '#475569', marginTop: '12px' }}>Máximo 8 MB</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Preview */}
              <div style={{ borderRadius: '12px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.08)', position: 'relative' }}>
                <img src={imagePreview} alt="Preview" style={{ width: '100%', maxHeight: '280px', objectFit: 'contain', background: '#0f172a', display: 'block' }} />
                <button onClick={resetState} style={{
                  position: 'absolute', top: '8px', right: '8px',
                  background: 'rgba(0,0,0,0.6)', border: 'none', cursor: 'pointer',
                  color: '#fff', borderRadius: '6px', padding: '4px 8px', fontSize: '11px',
                  display: 'flex', alignItems: 'center', gap: '4px', backdropFilter: 'blur(4px)',
                }}>
                  <X size={12} /> Cambiar
                </button>
                <div style={{
                  position: 'absolute', bottom: '8px', left: '8px',
                  background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
                  borderRadius: '6px', padding: '4px 10px', fontSize: '11px', color: '#94a3b8',
                }}>
                  {imageFile?.name} · {(imageFile?.size / 1024).toFixed(0)} KB
                </div>
              </div>

              {/* Loader */}
              {loading && (
                <div style={{
                  borderRadius: '12px', border: '1px solid rgba(139,92,246,0.2)',
                  background: 'rgba(139,92,246,0.06)', padding: '24px', textAlign: 'center',
                }}>
                  <Loader2 size={28} color="#8b5cf6" style={{ animation: 'spin 1s linear infinite', margin: '0 auto 12px' }} />
                  <div style={{ fontSize: '14px', color: '#a78bfa', fontWeight: 600 }}>Analizando imagen con IA...</div>
                  <div style={{ fontSize: '12px', color: '#64748b', marginTop: '6px' }}>Esto puede tardar unos segundos</div>
                </div>
              )}

              {/* Resultado */}
              {result && !loading && (
                <div style={{
                  borderRadius: '12px', padding: '16px',
                  border: `1px solid ${hasError ? 'rgba(239,68,68,0.3)' : hasClasses ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}`,
                  background: hasError ? 'rgba(239,68,68,0.06)' : hasClasses ? 'rgba(16,185,129,0.06)' : 'rgba(245,158,11,0.06)',
                }}>
                  <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', marginBottom: hasClasses ? '12px' : '8px' }}>
                    {hasError
                      ? <AlertCircle size={18} color="#ef4444" style={{ flexShrink: 0, marginTop: '2px' }} />
                      : hasClasses
                        ? <Check size={18} color="#10b981" style={{ flexShrink: 0, marginTop: '2px' }} />
                        : <AlertCircle size={18} color="#f59e0b" style={{ flexShrink: 0, marginTop: '2px' }} />
                    }
                    <div style={{ flex: 1 }}>
                      <div style={{
                        fontSize: '13px', fontWeight: 600, marginBottom: '6px',
                        color: hasError ? '#fca5a5' : hasClasses ? '#6ee7b7' : '#fcd34d',
                      }}>
                        {hasError ? (result.error.includes('tardó demasiado') ? 'Tiempo de espera agotado' : result.error.includes('Falta cargar') ? 'Modelo de visión no disponible' : result.error.includes('servidor local') ? 'Servidor de IA no disponible' : 'No se pudo analizar la imagen') : hasClasses ? `${result.nodes.length} clase(s) detectadas` : 'Sin clases detectadas'}
                      </div>
                      <div style={{ fontSize: '12px', color: '#94a3b8', lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                        {hasError ? result.error : result.description}
                      </div>
                    </div>
                  </div>

                  {hasClasses && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                      {result.nodes.map((n, i) => (
                        <div key={i} style={{
                          padding: '4px 10px', borderRadius: '6px', fontSize: '12px', fontWeight: 600,
                          background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.2)', color: '#6ee7b7',
                        }}>
                          {n.data?.name || n.id}
                          <span style={{ color: '#475569', fontWeight: 400, marginLeft: '4px' }}>
                            ({n.data?.attributes?.length || 0}a/{n.data?.methods?.length || 0}m)
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {result.model && result.model !== 'none' && (
                    <div style={{ fontSize: '10px', color: '#6366f1', marginTop: '10px' }}>🤖 {result.model}</div>
                  )}

                  {/* Botón de diagnóstico cuando falla */}
                  {(hasError || !hasClasses) && (
                    <div style={{ marginTop: '12px' }}>
                      <button
                        onClick={handleDiagnose}
                        disabled={diagnosing}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '6px',
                          padding: '7px 14px', borderRadius: '7px', border: '1px solid rgba(99,102,241,0.4)',
                          background: 'rgba(99,102,241,0.1)', color: '#a5b4fc',
                          cursor: diagnosing ? 'not-allowed' : 'pointer', fontSize: '12px', fontWeight: 600,
                        }}
                      >
                        {diagnosing
                          ? <><Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> Verificando...</>
                          : <><Stethoscope size={13} /> Verificar estado de APIs</>
                        }
                      </button>

                      {diagnoseResult && (
                        <div style={{ marginTop: '10px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          {Object.entries(diagnoseResult).map(([provider, info]) => (
                            <div key={provider} style={{
                              display: 'flex', alignItems: 'flex-start', gap: '8px',
                              padding: '8px 12px', borderRadius: '8px', fontSize: '12px',
                              background: info.status === 'ok' ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                              border: `1px solid ${info.status === 'ok' ? 'rgba(16,185,129,0.25)' : 'rgba(239,68,68,0.25)'}`,
                            }}>
                              <span style={{ fontSize: '14px' }}>{info.status === 'ok' ? '✅' : '❌'}</span>
                              <div>
                                <span style={{ fontWeight: 700, color: info.status === 'ok' ? '#6ee7b7' : '#fca5a5', textTransform: 'uppercase', fontSize: '10px' }}>{provider}</span>
                                <div style={{ color: '#94a3b8', marginTop: '2px' }}>{info.detail}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* Sugerencia al usuario mientras no ha analizado la imagen */}
              {!result && !loading && (
                <div style={{
                  borderRadius: '10px', padding: '12px 16px',
                  background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.2)',
                  fontSize: '12px', color: '#a5b4fc', lineHeight: 1.7,
                }}>
                  ✅ <strong>Imagen cargada.</strong> Haz clic en <strong>Analizar con IA</strong> para extraer las clases, relaciones y multiplicidades del diagrama.
                </div>
              )}
            </div>
          )}
          <input ref={fileInputRef} type="file" accept="image/*" onChange={(e) => processFile(e.target.files[0])} style={{ display: 'none' }} />
        </div>

        {/* Footer */}
        <div style={{
          padding: '16px 24px', borderTop: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', gap: '10px', justifyContent: 'flex-end', flexShrink: 0,
        }}>
          <button onClick={handleClose} style={{
            padding: '9px 18px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.1)',
            background: 'transparent', color: '#64748b', cursor: 'pointer', fontSize: '13px',
          }}>Cancelar</button>

          {imagePreview && !result && !loading && (
            <button onClick={handleAnalyze} style={{
              padding: '9px 20px', borderRadius: '8px', border: 'none',
              background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
              color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: '7px',
              boxShadow: '0 4px 15px rgba(139,92,246,0.35)',
            }}>
              <Sparkles size={14} /> Analizar con IA
            </button>
          )}

          {hasClasses && (
            <button onClick={handleApply} style={{
              padding: '9px 20px', borderRadius: '8px', border: 'none',
              background: 'linear-gradient(135deg, #10b981, #059669)',
              color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
              display: 'flex', alignItems: 'center', gap: '7px',
              boxShadow: '0 4px 15px rgba(16,185,129,0.35)',
            }}>
              <Check size={14} /> Aplicar al canvas ({result.nodes.length} clases)
            </button>
          )}

          {result && !hasClasses && !loading && (
            <button onClick={handleAnalyze} style={{
              padding: '9px 18px', borderRadius: '8px', border: 'none',
              background: 'rgba(139,92,246,0.2)', color: '#a78bfa', cursor: 'pointer', fontSize: '13px',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}>
              <Sparkles size={13} /> Reintentar
            </button>
          )}
        </div>
      </div>

      <style>{`
        @keyframes modalIn {
          from { opacity: 0; transform: translate(-50%, -52%) scale(0.95); }
          to   { opacity: 1; transform: translate(-50%, -50%) scale(1); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </>
  );
}
