/**
 * CollabStatus.jsx
 *
 * Barra / indicador flotante que muestra:
 *   - Estado de la conexión WebSocket (conectado / reconectando / desconectado)
 *   - Avatares de los colaboradores activos en la sala
 */

import React from 'react';
import { Wifi, WifiOff, Loader } from 'lucide-react';

const STATUS_CONFIG = {
  connected:    { icon: Wifi,    color: '#16a34a', label: 'En línea' },
  connecting:   { icon: Loader,  color: '#d97706', label: 'Conectando…' },
  disconnected: { icon: WifiOff, color: '#dc2626', label: 'Sin conexión' },
};

export default function CollabStatus({ wsStatus, collaborators, participants = {}, aiEnabled = false }) {
  const config = STATUS_CONFIG[wsStatus] || STATUS_CONFIG.disconnected;
  const Icon   = config.icon;
  const entries = Object.entries(collaborators);

  return (
    <div
      style={{
        position:     'absolute',
        bottom:       '16px',
        left:         '50%',
        transform:    'translateX(-50%)',
        zIndex:       10,
        display:      'flex',
        alignItems:   'center',
        gap:          '10px',
        background:   'rgba(255,255,255,0.97)',
        border:       '1px solid #e2e8f0',
        borderRadius: '30px',
        padding:      '6px 16px',
        boxShadow:    '0 4px 20px rgba(0,0,0,0.1)',
        fontSize:     '12px',
        fontFamily:   'Inter, system-ui, sans-serif',
      }}
    >
      {/* Indicador de estado */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '5px', color: config.color }}>
        <Icon size={13} style={wsStatus === 'connecting' ? { animation: 'spin 1s linear infinite' } : {}} />
        <span style={{ fontWeight: 600 }}>{config.label}</span>
      </div>

      {/* Separador */}
      {entries.length > 0 && (
        <div style={{ width: '1px', height: '16px', background: '#cbd5e1' }} />
      )}

      {/* Avatares de colaboradores */}
      {entries.map(([userId, collab]) => (
        <div
          key={userId}
          title={collab.username || participants[userId] || 'Alguien'}
          style={{
            width:        '26px',
            height:       '26px',
            borderRadius: '50%',
            background:   collab.color,
            display:      'flex',
            alignItems:   'center',
            justifyContent: 'center',
            color:        '#fff',
            fontWeight:   700,
            fontSize:     '11px',
            border:       '2px solid #fff',
            boxShadow:    '0 1px 4px rgba(0,0,0,0.15)',
            marginLeft:   '-6px',
            cursor:       'default',
          }}
        >
          {(collab.username || participants[userId] || 'Alguien')[0].toUpperCase()}
        </div>
      ))}

      {aiEnabled && <div title="Asistente IA · disponible para @ia" style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ width: 27, height: 27, borderRadius: '50%', background: '#4f46e5', color: '#fff',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800,
          border: '2px solid #fff', boxShadow: '0 1px 5px rgba(79,70,229,.35)' }}>✦</span>
        <span style={{ fontSize: 10, fontWeight: 800, color: '#4f46e5' }}>IA</span>
      </div>}

      {entries.length > 0 && (
        <span style={{ color: '#64748b', fontSize: '11px', marginLeft: '4px' }}>
          {entries.length} colaborador{entries.length !== 1 ? 'es' : ''} activo{entries.length !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  );
}
