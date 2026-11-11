import assert from 'node:assert/strict';
import test from 'node:test';
import { prepareVisionDiagram } from './prepareVisionDiagram.js';

const existing = [{ id: 'old', position: { x: 100, y: 20 }, width: 180, data: { name: 'Persona' } }];
const generated = [{ id: 'vision-a', position: { x: 80, y: 80 }, data: { name: 'Persona' } },
  { id: 'vision-b', position: { x: 380, y: 80 }, data: { name: 'Paciente' } }];
const links = [{ id: 'edge-vision-0', source: 'vision-b', target: 'vision-a', data: { relation_type: 'inheritance' } }];

test('agregar conserva el diagrama y remapea nombres, IDs y extremos', () => {
  let count = 0;
  const result = prepareVisionDiagram(existing, [], generated, links, 'add', prefix => `${prefix}-${++count}`);
  assert.equal(result.nodes.length, 3);
  assert.equal(result.nodes[1].data.name, 'Persona_2');
  assert.equal(result.nodes[1].position.x, 460);
  assert.equal(result.edges[0].source, result.nodes[2].id);
  assert.equal(result.edges[0].target, result.nodes[1].id);
  assert.notEqual(result.edges[0].id, links[0].id);
  assert.equal(existing[0].data.name, 'Persona');
});

test('reemplazar descarta el grafo anterior y conserva los nombres originales', () => {
  let count = 0;
  const result = prepareVisionDiagram(existing, [{ id: 'old-edge' }], generated, links, 'replace', prefix => `${prefix}-${++count}`);
  assert.equal(result.nodes.length, 2);
  assert.equal(result.edges.length, 1);
  assert.equal(result.nodes[0].data.name, 'Persona');
  assert.equal(result.nodes[0].position.x, 80);
});
