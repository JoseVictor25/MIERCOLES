import { useState } from 'react';

const RELATION_LABELS = {
  association: 'asociación', directed_association: 'asociación dirigida',
  aggregation: 'agregación', composition: 'composición',
  inheritance: 'herencia', dependency: 'dependencia',
  realization: 'realización', association_class: 'clase de asociación',
};

export default function XMIImportModal({ preview, onCancel, onImport }) {
  const [mode, setMode] = useState('add');
  const [busy, setBusy] = useState(false);
  const counts = Object.entries(preview.relations || {});
  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: '#0009', display: 'grid', placeItems: 'center' }}>
      <div role="dialog" aria-modal="true" aria-label="Vista previa de XMI" style={{ width: 'min(520px, 92vw)', maxHeight: '85vh', overflowY: 'auto', padding: 24, borderRadius: 14, background: '#fff', color: '#1e293b', boxShadow: '0 18px 55px #0005' }}>
        <h2 style={{ marginTop: 0, fontSize: 19 }}>Importar XMI/XML</h2>
        <p><strong>{preview.classes}</strong> clases, interfaces o enumeraciones</p>
        <p>Relaciones: {counts.length ? counts.map(([type, number]) => `${RELATION_LABELS[type] || type}: ${number}`).join(' · ') : 'ninguna'}</p>
        {preview.warnings?.length > 0 && <div style={{ background: '#fffbeb', border: '1px solid #fbbf24', borderRadius: 8, padding: 10 }}><strong>Advertencias</strong><ul>{preview.warnings.map((warning, i) => <li key={i}>{warning}</li>)}</ul></div>}
        <div style={{ display: 'grid', gap: 9, margin: '18px 0' }}>
          <label><input type="radio" name="xmi-mode" checked={mode === 'add'} onChange={() => setMode('add')} /> Agregar al diagrama actual</label>
          <label><input type="radio" name="xmi-mode" checked={mode === 'replace'} onChange={() => setMode('replace')} /> Reemplazar el diagrama</label>
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button className="btn btn-secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
          <button className="btn btn-primary" disabled={busy} onClick={async () => { setBusy(true); try { await onImport(mode); } finally { setBusy(false); } }}>Importar</button>
        </div>
      </div>
    </div>
  );
}
