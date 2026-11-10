import React, { useState, useEffect } from 'react';
import { Download, FileCode, Package, Server, Layers, X, CheckCircle2 } from 'lucide-react';
import { toast } from 'react-hot-toast';
import api from '../api/axios';

export default function GenerateBackendModal({ isOpen, onClose, project, nodes = [], edges = [], onSaveBeforeGenerate }) {
  const [groupId, setGroupId] = useState('com.example');
  const [artifactId, setArtifactId] = useState('');
  const [includeAiDocs, setIncludeAiDocs] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);

  useEffect(() => {
    if (project?.name) {
      const cleanSlug = project.name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');
      setArtifactId(cleanSlug || 'backend');
    }
  }, [project]);

  if (!isOpen || !project) return null;

  const classCount = nodes.length;
  const relationCount = edges.length;

  const handleGenerate = async (e) => {
    e.preventDefault();
    setIsGenerating(true);
    const toastId = toast.loading('Generando proyecto Spring Boot en 5 capas...');

    try {
      const saved = await onSaveBeforeGenerate();
      if (!saved) {
        toast.error('No se pudo guardar el diagrama. No se generó el backend.', { id: toastId });
        return;
      }
      const response = await api.post(
        `projects/${project.id}/generate/spring-boot/`,
        {
          group_id: groupId.trim() || 'com.example',
          artifact_id: artifactId.trim() || 'backend',
          include_ai_docs: includeAiDocs,
        },
        {
          responseType: 'blob',
        }
      );

      // Crear URL de descarga del Blob
      const blob = new Blob([response.data], { type: 'application/zip' });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      const filename = `${artifactId.trim() || 'proyecto'}-backend.zip`;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);

      toast.success('¡Backend Spring Boot descargado exitosamente!', { id: toastId });
      onClose();
    } catch (err) {
      toast.error('Error al generar el backend Spring Boot', { id: toastId });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 130,
      }}
      onClick={onClose}
    >
      <div
        className="glass-panel"
        style={{
          width: '520px',
          maxWidth: '92vw',
          maxHeight: '90vh',
          display: 'flex',
          flexDirection: 'column',
          padding: '26px',
          borderRadius: '18px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
          border: '1px solid rgba(255, 255, 255, 0.12)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '12px',
                background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#ffffff',
                boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
              }}
            >
              <Server size={22} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--text-main)' }}>
                Generar Backend Spring Boot
              </h3>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Proyecto: <strong style={{ color: 'var(--text-main)' }}>{project.name}</strong>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Resumen del Modelo */}
        <div
          style={{
            display: 'flex',
            gap: '12px',
            marginBottom: '20px',
            padding: '12px 16px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: '12px',
            border: '1px solid rgba(255, 255, 255, 0.06)',
          }}
        >
          <div style={{ flex: 1, textAlign: 'center', borderRight: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#10b981' }}>{classCount}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Clases Detectadas</div>
          </div>
          <div style={{ flex: 1, textAlign: 'center', borderRight: '1px solid rgba(255,255,255,0.08)' }}>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#60a5fa' }}>{relationCount}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Relaciones UML</div>
          </div>
          <div style={{ flex: 1, textAlign: 'center' }}>
            <div style={{ fontSize: '20px', fontWeight: 'bold', color: '#a78bfa' }}>5</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Capas de Software</div>
          </div>
        </div>

        {/* 5 Capas Incluidas */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
            Arquitectura Generada (5 Capas + Config)
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-main)' }}>
              <CheckCircle2 size={13} color="#10b981" /> 1. Entidades JPA (`entity/`)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-main)' }}>
              <CheckCircle2 size={13} color="#10b981" /> 2. DTOs Request/Response (`dto/`)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-main)' }}>
              <CheckCircle2 size={13} color="#10b981" /> 3. Conversores (`mapper/`)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-main)' }}>
              <CheckCircle2 size={13} color="#10b981" /> 4. Repositorios JPA (`repository/`)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-main)' }}>
              <CheckCircle2 size={13} color="#10b981" /> 5. Servicios e Impl (`service/`)
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: 'var(--text-main)' }}>
              <CheckCircle2 size={13} color="#10b981" /> 6. Controladores REST (`controller/`)
            </div>
          </div>
        </div>

        {/* Formulario de Configuración Maven */}
        <form onSubmit={handleGenerate} style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', fontWeight: 500 }}>
              Group ID (Dominio)
            </label>
            <div style={{ position: 'relative' }}>
              <Package size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text"
                className="input-field"
                value={groupId}
                onChange={(e) => setGroupId(e.target.value)}
                placeholder="com.example"
                style={{ paddingLeft: '36px', width: '100%', fontSize: '13px' }}
                required
              />
            </div>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '13px', marginBottom: '6px', fontWeight: 500 }}>
              Artifact ID (Nombre del Módulo)
            </label>
            <div style={{ position: 'relative' }}>
              <FileCode size={15} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
              <input
                type="text"
                className="input-field"
                value={artifactId}
                onChange={(e) => setArtifactId(e.target.value)}
                placeholder="backend"
                style={{ paddingLeft: '36px', width: '100%', fontSize: '13px' }}
                required
              />
            </div>
          </div>

          <div
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              background: 'rgba(59, 130, 246, 0.08)',
              border: '1px solid rgba(59, 130, 246, 0.2)',
              fontSize: '11px',
              color: '#93c5fd',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Layers size={13} />
            <span>
              Paquete raíz: <strong>{groupId || 'com.example'}.{artifactId || 'backend'}</strong> (Java 17 + Maven + H2/PostgreSQL)
            </span>
          </div>

          {/* Opción IA */}
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', marginTop: '2px' }}>
            <input
              type="checkbox"
              checked={includeAiDocs}
              onChange={(e) => setIncludeAiDocs(e.target.checked)}
              style={{ width: '16px', height: '16px', accentColor: '#10b981' }}
            />
            <span style={{ color: 'var(--text-main)', fontWeight: 500 }}>
              ✨ Incluir Documentación asistida por IA (JavaDoc y Swagger)
            </span>
          </label>

          {/* Botones de acción */}
          <div style={{ display: 'flex', gap: '10px', marginTop: '10px' }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isGenerating}
              style={{ flex: 1, padding: '9px 16px', fontSize: '13px' }}
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isGenerating}
              style={{
                flex: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '9px 16px',
                fontSize: '13px',
                fontWeight: 600,
                background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                color: '#ffffff',
                border: 'none',
                borderRadius: '8px',
                cursor: isGenerating ? 'not-allowed' : 'pointer',
                boxShadow: '0 4px 14px rgba(16, 185, 129, 0.4)',
              }}
            >
              <Download size={16} />
              {isGenerating ? 'Generando ZIP...' : 'Generar y Descargar (.ZIP)'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
