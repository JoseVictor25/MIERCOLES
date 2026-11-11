import { useRef } from 'react';
import {
  Save,
  ImageDown,
  Clock,
  Download,
  Users,
  Image,
  MessageSquare,
  ArrowLeft,
  Trash2,
  FileUp,
  FileDown,
  Undo2,
  Redo2,
} from 'lucide-react';

export default function StarUMLMenuBar({
  projectName,
  user,
  onBack,
  onSave,
  onExportPNG,
  onOpenHistory,
  onOpenAssistant,
  chatUnread = 0,
  onOpenImageToUML,
  onOpenGenerate,
  onOpenCollab,
  onExportXMI,
  onImportXMI,
  onDeleteProject,
  canEdit = false,
  collaboratorsCount = 0,
  isOwner = false,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
}) {
  const fileInputRef = useRef(null);

  const handleImportClick = () => {
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  return (
    <header
      style={{
        background: '#1e1e1e',
        borderBottom: '1px solid #333333',
        color: '#cccccc',
        height: '42px',
        minHeight: '42px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 12px',
        fontSize: '12px',
        fontFamily: 'Segoe UI, -apple-system, BlinkMacSystemFont, Roboto, sans-serif',
        userSelect: 'none',
        zIndex: 50,
      }}
    >
      {/* ── Izquierda: Navegación y Nombre del Proyecto ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <button
          onClick={onBack}
          style={actionBtnStyle}
          title="Volver a lista de proyectos"
        >
          <ArrowLeft size={14} />
          <span style={{ fontSize: '11px' }}>Proyectos</span>
        </button>

        <div style={dividerStyle} />

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              fontWeight: 600,
              fontSize: '13px',
              color: '#ffffff',
              letterSpacing: '0.01em',
              maxWidth: '240px',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {projectName || 'Diagrama UML'}
          </span>
          {user && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                background: '#2a2d2e',
                padding: '2px 8px',
                borderRadius: '10px',
                fontSize: '10px',
                color: '#9cdcfe',
              }}
            >
              <span
                style={{
                  width: '6px',
                  height: '6px',
                  borderRadius: '50%',
                  background: '#4ec9b0',
                }}
              />
              {user.username || user.email}
            </span>
          )}
        </div>
      </div>

      {/* ── Derecha: Acciones Rápidas del Diagrama ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
        {/* Deshacer (Ctrl+Z) y Rehacer (Ctrl+Y) */}
        <button
          onClick={onUndo}
          disabled={!canUndo}
          style={{
            ...actionBtnStyle,
            opacity: canUndo ? 1 : 0.4,
            cursor: canUndo ? 'pointer' : 'not-allowed',
          }}
          title="Deshacer última acción (Ctrl + Z)"
        >
          <Undo2 size={13} color={canUndo ? '#9cdcfe' : '#6b7280'} />
          <span>Deshacer</span>
        </button>

        <button
          onClick={onRedo}
          disabled={!canRedo}
          style={{
            ...actionBtnStyle,
            opacity: canRedo ? 1 : 0.4,
            cursor: canRedo ? 'pointer' : 'not-allowed',
          }}
          title="Rehacer acción (Ctrl + Y o Ctrl + Shift + Z)"
        >
          <Redo2 size={13} color={canRedo ? '#9cdcfe' : '#6b7280'} />
          <span>Rehacer</span>
        </button>

        <div style={dividerStyle} />

        <button
          onClick={onSave}
          style={actionBtnStyle}
          title="Guardar cambios del diagrama (PostgreSQL)"
        >
          <Save size={13} color="#4ec9b0" />
          <span>Guardar</span>
        </button>

        <button
          onClick={onExportPNG}
          style={actionBtnStyle}
          title="Exportar diagrama en formato de imagen PNG"
        >
          <ImageDown size={13} />
          <span>Exportar PNG</span>
        </button>

        <button
          onClick={onOpenHistory}
          style={actionBtnStyle}
          title="Historial de versiones y restauración de estados previos"
        >
          <Clock size={13} />
          <span>Historial</span>
        </button>

        <div style={dividerStyle} />

        <button
          onClick={onOpenImageToUML}
          style={actionBtnStyle}
          title="Importar diagrama desde foto o imagen escaneada"
        >
          <Image size={13} color="#ce9178" />
          <span>Importar Imagen</span>
        </button>

        <div style={dividerStyle} />

        <button
          onClick={() => onExportXMI('2.5.1')}
          style={actionBtnStyle}
          title="Exportar XMI UML 2.5.1"
        >
          <FileDown size={13} color="#60a5fa" />
          <span>Exportar XMI (UML 2.5.1)</span>
        </button>

        <button onClick={() => onExportXMI('2.1')} style={actionBtnStyle} title="Formato de compatibilidad XMI 2.1">
          <FileDown size={13} color="#60a5fa" />
          <span>Exportar XMI 2.1 (compatibilidad)</span>
        </button>

        {canEdit && <button
          onClick={handleImportClick}
          style={actionBtnStyle}
          title="Importar XMI/XML"
        >
          <FileUp size={13} color="#f472b6" />
          <span>Importar XMI/XML...</span>
        </button>}
        <input 
          type="file" 
          accept=".xmi,.xml" 
          ref={fileInputRef} 
          style={{ display: 'none' }} 
          onChange={onImportXMI} 
        />

        <div style={dividerStyle} />

        <button
          onClick={onOpenAssistant}
          style={actionBtnStyle}
          title="Abrir asistente de modelado UML"
        >
          <MessageSquare size={13} color="#9cdcfe" />
          <span>Chat</span>
          {chatUnread > 0 && <span style={{ background: '#dc2626', color: '#fff', borderRadius: 10, padding: '1px 5px' }}>{chatUnread}</span>}
        </button>

        <button
          onClick={onOpenGenerate}
          style={{
            ...actionBtnStyle,
            background: '#0e639c',
            borderColor: '#1177bb',
            color: '#ffffff',
            fontWeight: 500,
          }}
          title="Generar proyecto Spring Boot en 5 capas (.zip)"
        >
          <Download size={13} />
          <span>Generar Backend</span>
        </button>

        <div style={dividerStyle} />

        <button
          onClick={onOpenCollab}
          style={actionBtnStyle}
          title="Gestionar colaboradores en tiempo real"
        >
          <Users size={13} color="#dcdcaa" />
          <span>Colaboradores ({collaboratorsCount})</span>
        </button>

        {isOwner && (
          <button
            onClick={onDeleteProject}
            style={{
              ...actionBtnStyle,
              background: 'transparent',
              borderColor: 'transparent',
              color: '#f87171',
              padding: '4px 6px',
            }}
            title="Eliminar este proyecto"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </header>
  );
}

const actionBtnStyle = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '5px',
  padding: '4px 10px',
  background: '#2d2d30',
  color: '#cccccc',
  border: '1px solid #3e3e42',
  borderRadius: '3px',
  fontSize: '11px',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
  height: '27px',
};

const dividerStyle = {
  width: '1px',
  height: '18px',
  background: '#383838',
  margin: '0 4px',
};
