import test from 'node:test';
import assert from 'node:assert/strict';
import { applyAIUpdates } from './applyAIUpdates.js';

const nodes = [
  { id: 'rol', data: { name: 'Rol', attributes: [] } },
  { id: 'cliente', data: { name: 'Cliente', attributes: [] } },
];
const edges = [{ id: 'rel', source: 'cliente', target: 'rol',
  data: { relation_type: 'association', sourceMultiplicity: '', targetMultiplicity: '' } }];

test('cambia tipo y multiplicidades aunque la arista esté invertida', () => {
  const result = applyAIUpdates(nodes, edges, [
    { action: 'update_relation_type', source_class: 'Rol', target_class: 'Cliente', relation_type: 'inheritance' },
    { action: 'set_multiplicity', source_class: 'Rol', target_class: 'Cliente', source_multiplicity: '1', target_multiplicity: '1..*' },
  ]);
  assert.equal(result.applied.length, 2);
  assert.equal(result.edges[0].data.relation_type, 'inheritance');
  assert.equal(result.edges[0].source, 'rol');
  assert.equal(result.edges[0].target, 'cliente');
  assert.equal(result.edges[0].data.sourceMultiplicity, '1');
  assert.equal(result.edges[0].data.targetMultiplicity, '1..*');
  assert.equal(edges[0].data.relation_type, 'association');
});

test('renombra y rechaza cambios sin efecto', () => {
  const result = applyAIUpdates(nodes, edges, [
    { action: 'rename_class', name: 'Rol', new_name: 'Perfil' },
    { action: 'delete_relation', source_class: 'Perfil', target_class: 'Desconocido' },
  ]);
  assert.equal(result.nodes[0].data.name, 'Perfil');
  assert.equal(result.applied.length, 1);
  assert.equal(result.failed.length, 1);
});
