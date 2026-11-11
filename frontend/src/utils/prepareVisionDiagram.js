// Crea identificadores nuevos y evita pisar elementos al aplicar una conversión de imagen.
const newId = prefix => `${prefix}-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;

export function prepareVisionDiagram(currentNodes, currentEdges, visionNodes, visionEdges, mode = 'add', makeId = newId) {
  const replace = mode === 'replace';
  const names = new Set(replace ? [] : currentNodes.map(node => node.data?.name));
  const idMap = new Map();
  const offset = !replace && currentNodes.length
    ? Math.max(...currentNodes.map(node => (node.position?.x || 0) + (node.width || 180))) + 100 : 0;
  const importedNodes = visionNodes.map((node, index) => {
    let name = node.data?.name || `Clase${index + 1}`;
    if (names.has(name)) {
      const base = name;
      let suffix = 2;
      while (names.has(`${base}_${suffix}`)) suffix++;
      name = `${base}_${suffix}`;
    }
    names.add(name);
    const id = makeId('class');
    idMap.set(node.id, id);
    return { ...node, id,
      position: { x: (node.position?.x || 0) + offset, y: node.position?.y || 0 },
      data: { ...node.data, id, name } };
  });
  const importedEdges = (visionEdges || []).filter(edge => idMap.has(edge.source) && idMap.has(edge.target))
    .map(edge => ({ ...edge, id: makeId('edge'), source: idMap.get(edge.source), target: idMap.get(edge.target),
      reconnectable: true, data: { ...edge.data,
        ...(edge.data?.associationClassId ? { associationClassId: idMap.get(edge.data.associationClassId) } : {}) } }));
  return {
    nodes: replace ? importedNodes : [...currentNodes, ...importedNodes],
    edges: replace ? importedEdges : [...currentEdges, ...importedEdges],
  };
}
