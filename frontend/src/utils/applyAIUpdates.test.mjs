import assert from 'node:assert/strict';
import test from 'node:test';
import { applyAIUpdates } from './applyAIUpdates.js';

const nodes = [
  { id: 'm', data: { name: 'Medico', is_abstract: false,
    attributes: [{ id: 'a', name: 'nombre', data_type: 'String' }, { id: 'b', name: 'edad', data_type: 'int' }],
    methods: [] } },
  { id: 'p', data: { name: 'Persona', attributes: [], methods: [] } },
];

test('reordena y modifica atributos conservando los identificadores', () => {
  const result = applyAIUpdates(nodes, [], [
    { action: 'reorder_attributes', class_name: 'Medico', order: ['edad', 'nombre'] },
    { action: 'update_attribute', class_name: 'Medico', attr_name: 'edad', data_type: 'Integer' },
  ]);
  assert.equal(result.applied.length, 2);
  assert.deepEqual(result.nodes[0].data.attributes.map(attr => attr.id), ['b', 'a']);
  assert.equal(result.nodes[0].data.attributes[0].data_type, 'Integer');
  assert.deepEqual(nodes[0].data.attributes.map(attr => attr.id), ['a', 'b']);
});

test('aplica abstracción y métodos y acepta los ocho tipos de relación', () => {
  const types = ['association', 'directed_association', 'dependency', 'aggregation',
    'composition', 'inheritance', 'realization', 'association_class'];
  for (const relation_type of types) {
    const result = applyAIUpdates(nodes, [], [
      { action: 'set_abstract', name: 'Medico', is_abstract: true },
      { action: 'add_method', class_name: 'Medico', method_name: 'atender', return_type: 'void' },
      { action: 'add_relation', source_class: 'Medico', target_class: 'Persona', relation_type,
        source_multiplicity: '1', target_multiplicity: '*', label: 'atiende' },
    ]);
    assert.equal(result.applied.length, 3);
    assert.equal(result.nodes[0].data.is_abstract, true);
    assert.equal(result.nodes[0].data.methods[0].name, 'atender');
    assert.equal(result.edges[0].source, 'm');
    assert.equal(result.edges[0].target, 'p');
    assert.equal(result.edges[0].data.label, 'atiende');
    assert.equal(result.edges[0].data.targetMultiplicity, '*');
    assert.equal(applyAIUpdates(result.nodes, result.edges, [
      { action: 'delete_method', class_name: 'Medico', method_name: 'atender' },
    ]).nodes[0].data.methods.length, 0);
  }
});
