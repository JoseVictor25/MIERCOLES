// Aplica propuestas de la IA sin modificar los arreglos originales.
export function applyAIUpdates(nodes, edges, updates) {
  const relationTypes = new Set(['association', 'directed_association', 'dependency',
    'aggregation', 'composition', 'inheritance', 'realization', 'association_class']);
  let resultNodes = [...nodes];
  let resultEdges = [...edges];
  const applied = [];
  const failed = [];
  let serial = 0;
  const id = (prefix) => `${prefix}-ai-${Date.now()}-${serial++}`;
  const findNode = (name) => resultNodes.find(n => n.data?.name?.toLowerCase() === String(name || '').toLowerCase());
  const findEdge = (a, b) => {
    const src = findNode(a), tgt = findNode(b);
    if (!src || !tgt) return null;
    return resultEdges.find(e => (e.source === src.id && e.target === tgt.id) ||
      (e.source === tgt.id && e.target === src.id));
  };

  for (const update of updates || []) {
    const action = update?.action;
    const node = findNode(update?.name || update?.class_name);
    const edge = findEdge(update?.source_class, update?.target_class);
    let reason = '';
    if (action === 'add_class') {
      if (!update.name || findNode(update.name)) reason = 'La clase ya existe o no tiene nombre.';
      else {
        const nodeId = id('class');
        resultNodes.push({ id: nodeId, type: 'classNode',
          position: { x: 300 + serial * 30, y: 200 + serial * 30 },
          data: { id: nodeId, name: update.name, is_abstract: false, attributes: [], methods: [] } });
      }
    } else if (action === 'delete_class') {
      if (!node) reason = 'La clase no existe.';
      else {
        resultNodes = resultNodes.filter(n => n.id !== node.id);
        resultEdges = resultEdges.filter(e => e.source !== node.id && e.target !== node.id);
      }
    } else if (action === 'rename_class') {
      if (!node || !update.new_name || findNode(update.new_name)) reason = 'No se puede renombrar la clase.';
      else resultNodes = resultNodes.map(n => n.id === node.id ? { ...n, data: { ...n.data, name: update.new_name } } : n);
    } else if (action === 'set_abstract') {
      if (!node || typeof update.is_abstract !== 'boolean') reason = 'Clase o estado abstracto inválido.';
      else if (Boolean(node.data?.is_abstract) === update.is_abstract) reason = 'La clase ya tiene ese estado.';
      else resultNodes = resultNodes.map(n => n.id === node.id ? {
        ...n, data: { ...n.data, is_abstract: update.is_abstract },
      } : n);
    } else if (['add_attribute', 'delete_attribute', 'update_attribute', 'reorder_attributes'].includes(action)) {
      const target = findNode(update.class_name);
      const attrs = target?.data?.attributes || [];
      const exists = attrs.some(a => a.name?.toLowerCase() === String(update.attr_name || '').toLowerCase());
      if (!target) reason = 'La clase no existe.';
      else if (action === 'reorder_attributes') {
        const order = Array.isArray(update.order) ? update.order.map(name => String(name).toLowerCase()) : [];
        const ordered = [];
        for (const name of order) {
          const attr = attrs.find(item => item.name?.toLowerCase() === name);
          if (attr && !ordered.includes(attr)) ordered.push(attr);
        }
        const next = [...ordered, ...attrs.filter(attr => !ordered.includes(attr))];
        if (!order.length || next.every((attr, index) => attr === attrs[index])) reason = 'Los atributos ya están en ese orden.';
        else resultNodes = resultNodes.map(n => n.id === target.id ? { ...n, data: { ...n.data, attributes: next } } : n);
      } else if (!update.attr_name || update.attr_name.toLowerCase() === 'multiplicidad') reason = 'Nombre de atributo inválido.';
      else if (action === 'add_attribute' && exists) reason = 'El atributo ya existe.';
      else if (action === 'delete_attribute' && !exists) reason = 'El atributo no existe.';
      else if (action === 'update_attribute' && !exists) reason = 'El atributo no existe.';
      else if (action === 'update_attribute' && !['new_name', 'data_type', 'visibility'].some(key => update[key])) reason = 'Falta indicar qué cambiar.';
      else if (action === 'update_attribute' && update.new_name && attrs.some(a =>
        a.name?.toLowerCase() === update.new_name.toLowerCase() &&
        a.name?.toLowerCase() !== update.attr_name.toLowerCase())) reason = 'El nuevo nombre ya existe.';
      else {
        const next = action === 'add_attribute'
          ? [...attrs, { id: id('attr'), name: update.attr_name, data_type: update.data_type || 'String', visibility: update.visibility || '-' }]
          : action === 'delete_attribute'
            ? attrs.filter(a => a.name?.toLowerCase() !== update.attr_name.toLowerCase())
            : attrs.map(a => a.name?.toLowerCase() === update.attr_name.toLowerCase() ? {
              ...a, name: update.new_name || a.name, data_type: update.data_type || a.data_type,
              visibility: update.visibility || a.visibility,
            } : a);
        if (action === 'update_attribute' && JSON.stringify(next) === JSON.stringify(attrs)) reason = 'El atributo ya tiene esos valores.';
        if (!reason) resultNodes = resultNodes.map(n => n.id === target.id ? { ...n, data: { ...n.data, attributes: next } } : n);
      }
    } else if (action === 'add_method' || action === 'delete_method') {
      const target = findNode(update.class_name);
      const methods = target?.data?.methods || [];
      const exists = methods.some(m => m.name?.toLowerCase() === String(update.method_name || '').toLowerCase());
      if (!target || !update.method_name) reason = 'Clase o método inválido.';
      else if (action === 'add_method' && exists) reason = 'El método ya existe.';
      else if (action === 'delete_method' && !exists) reason = 'El método no existe.';
      else {
        const next = action === 'add_method'
          ? [...methods, { id: id('method'), name: update.method_name, return_type: update.return_type || 'void', visibility: '+', parameters: [] }]
          : methods.filter(m => m.name?.toLowerCase() !== update.method_name.toLowerCase());
        resultNodes = resultNodes.map(n => n.id === target.id ? { ...n, data: { ...n.data, methods: next } } : n);
      }
    } else if (action === 'add_relation') {
      const source = findNode(update.source_class), target = findNode(update.target_class);
      if (!source || !target || source.id === target.id || edge) reason = 'Las clases no existen o la relación ya existe.';
      else if (!relationTypes.has(update.relation_type || 'association')) reason = 'Tipo de relación inválido.';
      else resultEdges.push({ id: id('edge'), type: 'umlEdge', reconnectable: true,
        source: source.id, target: target.id, sourceHandle: 'bottom-source', targetHandle: 'top-target',
        data: { relation_type: update.relation_type || 'association',
          sourceMultiplicity: update.source_multiplicity || '', targetMultiplicity: update.target_multiplicity || '',
          label: update.label || '' } });
    } else if (action === 'delete_relation') {
      if (!edge) reason = 'La relación no existe.';
      else resultEdges = resultEdges.filter(e => e.id !== edge.id);
    } else if (action === 'update_relation_type' || action === 'set_multiplicity') {
      if (!edge) reason = 'La relación no existe.';
      else if (action === 'update_relation_type' && !relationTypes.has(update.relation_type)) reason = 'Tipo de relación inválido.';
      else {
        const forward = findNode(update.source_class)?.id === edge.source;
        const data = action === 'update_relation_type'
          ? { ...edge.data, relation_type: update.relation_type }
          : { ...edge.data,
            sourceMultiplicity: forward ? update.source_multiplicity : update.target_multiplicity,
            targetMultiplicity: forward ? update.target_multiplicity : update.source_multiplicity };
        const reverseInheritance = action === 'update_relation_type' && update.relation_type === 'inheritance' && !forward;
        if (reverseInheritance) {
          [data.sourceMultiplicity, data.targetMultiplicity] = [data.targetMultiplicity, data.sourceMultiplicity];
        }
        if (JSON.stringify(data) === JSON.stringify(edge.data) && !reverseInheritance) reason = 'La relación ya tiene esos valores.';
        else resultEdges = resultEdges.map(e => e.id === edge.id ? {
          ...e,
          ...(reverseInheritance ? { source: edge.target, target: edge.source } : {}),
          data,
        } : e);
      }
    } else reason = 'Acción desconocida.';
    if (reason) failed.push({ update, reason });
    else applied.push(update);
  }
  return { nodes: resultNodes, edges: resultEdges, applied, failed };
}
