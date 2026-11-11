import { useEffect, useState } from 'react';
import { Image as ImageIcon, Loader2, Sparkles, X } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../api/axios';

export default function ChatImageCard({ message, projectId, canWrite, onApplyImage }) {
  const [thumbnailUrl, setThumbnailUrl] = useState(null);
  const [fullUrl, setFullUrl] = useState(null);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [result, setResult] = useState(null);
  const [mode, setMode] = useState('add');
  const [imageError, setImageError] = useState(false);

  useEffect(() => {
    let active = true;
    let objectUrl;
    api.get(message.meta.thumbnail_url, { responseType: 'blob' }).then(({ data }) => {
      objectUrl = URL.createObjectURL(data);
      if (active) setThumbnailUrl(objectUrl);
      else URL.revokeObjectURL(objectUrl);
    }).catch(() => { if (active) setImageError(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [message.meta.thumbnail_url]);

  useEffect(() => () => { if (fullUrl) URL.revokeObjectURL(fullUrl); }, [fullUrl]);

  const openFull = async () => {
    try {
      const { data } = await api.get(message.meta.image_url, { responseType: 'blob' });
      setFullUrl(URL.createObjectURL(data));
    } catch {
      toast.error('No se pudo abrir la imagen.');
    }
  };

  const analyze = async () => {
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.post(`projects/${projectId}/chat/${message.id}/analyze/`, {}, { timeout: 620000 });
      setResult(data);
      if (data.error) toast.error(data.error);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'No se pudo analizar la imagen.');
    } finally {
      setLoading(false);
    }
  };

  const apply = async () => {
    setApplying(true);
    try {
      const applied = await onApplyImage(result.nodes, result.edges || [], mode);
      if (applied) {
        toast.success('Diagrama agregado al lienzo compartido.');
        setResult(null);
      } else {
        toast.error('No se pudo guardar el diagrama. Intenta de nuevo.');
      }
    } catch {
      toast.error('No se pudo aplicar el diagrama.');
    } finally {
      setApplying(false);
    }
  };

  return <div className="project-chat-image-card">
    {thumbnailUrl ? <button className="project-chat-image-open" onClick={openFull} title="Abrir imagen completa">
      <img src={thumbnailUrl} alt={message.content || 'Diagrama de clases compartido'} />
    </button> : <div className="project-chat-image-placeholder"><ImageIcon size={20} />
      {imageError ? 'No se pudo cargar la imagen' : 'Cargando imagen…'}</div>}
    <div className="project-chat-image-info">
      <ImageIcon size={13} /> Imagen compartida · {message.meta.width} × {message.meta.height} px
    </div>
    {canWrite && <button className="project-chat-image-analyze" onClick={analyze} disabled={loading || applying}>
      {loading ? <Loader2 size={14} className="project-chat-spin" /> : <Sparkles size={14} />}
      {loading ? 'Analizando imagen…' : 'Convertir a UML'}
    </button>}
    {result && <div className="project-chat-image-result">
      {result.error ? <p role="alert">{result.error}</p> : <>
        <strong>{result.nodes?.length || 0} clases · {result.edges?.length || 0} relaciones detectadas</strong>
        <div className="project-chat-image-class-list">{result.nodes?.map(node => <span key={node.id}>{node.data?.name}</span>)}</div>
        {result.description && <p>{result.description}</p>}
        <div className="project-chat-image-options">
          <label><input type="radio" name={`chat-image-mode-${message.id}`} checked={mode === 'add'} onChange={() => setMode('add')} /> Agregar</label>
          <label><input type="radio" name={`chat-image-mode-${message.id}`} checked={mode === 'replace'} onChange={() => setMode('replace')} /> Reemplazar</label>
        </div>
        <div className="project-chat-image-actions">
          <button onClick={() => setResult(null)}>Cancelar</button>
          <button onClick={apply} disabled={applying || !result.nodes?.length}>
            {applying ? 'Guardando…' : 'Enviar al lienzo'}
          </button>
        </div>
      </>}
    </div>}
    {fullUrl && <div className="project-chat-image-overlay" onClick={() => setFullUrl(null)}>
      <button onClick={() => setFullUrl(null)} aria-label="Cerrar imagen"><X size={20} /></button>
      <img src={fullUrl} alt={message.content || 'Diagrama de clases compartido'} onClick={event => event.stopPropagation()} />
    </div>}
  </div>;
}
