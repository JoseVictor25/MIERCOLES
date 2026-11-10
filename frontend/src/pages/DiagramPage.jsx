import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ReactFlow,
  ReactFlowProvider,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  addEdge,
  reconnectEdge,
  getNodesBounds,
  getViewportForBounds,
  useReactFlow,
  SelectionMode,
  useViewport,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { toPng } from 'html-to-image';
import { ArrowLeft, Plus, Save, Trash2, PlusCircle, Users, Download, Pencil, Check, X, ImageDown, Clock, Sparkles } from 'lucide-react';
import toast from 'react-hot-toast';
import api from '../api/axios';
import ClassNode from '../components/ClassNode';
import UMLEdge from '../components/UMLEdge';
import UMLMarkers from '../components/UMLMarkers';
import CollaboratorCursors from '../components/CollaboratorCursors';
import CollabStatus from '../components/CollabStatus';
import CollaboratorsModal from '../components/CollaboratorsModal';
import GenerateBackendModal from '../components/GenerateBackendModal';
import HistoryModal from '../components/HistoryModal';
import AIChatPanel from '../components/AIChatPanel';
import ImageToUMLModal from '../components/ImageToUMLModal';
import StarUMLMenuBar from '../components/StarUMLMenuBar';
import StarUMLToolbox from '../components/StarUMLToolbox';
import HelpChatBot from '../components/HelpChatBot';
import { useCollaboration } from '../hooks/useCollaboration';
import { useProjectStore } from '../store/projectStore';
import { useAuthStore } from '../store/authStore';

function SyncHorizontalScrollbar() {
  const { x, y, zoom } = useViewport();
  const { setViewport } = useReactFlow();
  const scrollContainerRef = useRef(null);
  const isSyncingFromFlow = useRef(false);
  const isSyncingFromScroll = useRef(false);
  
  const VIRTUAL_WIDTH = 5000;
  
  useEffect(() => {
    if (isSyncingFromScroll.current) {
      isSyncingFromScroll.current = false;
      return;
    }
    if (scrollContainerRef.current) {
      isSyncingFromFlow.current = true;
      scrollContainerRef.current.scrollLeft = -x + (VIRTUAL_WIDTH / 2);
    }
  }, [x]);

  const onScroll = (e) => {
    if (isSyncingFromFlow.current) {
      isSyncingFromFlow.current = false;
      return;
    }
    isSyncingFromScroll.current = true;
    const newX = -(e.target.scrollLeft - (VIRTUAL_WIDTH / 2));
    setViewport({ x: newX, y, zoom });
  };

  return (
    <div
      ref={scrollContainerRef}
      onScroll={onScroll}
      style={{
        position: 'absolute',
        bottom: 25,
        left: 0,
        right: 14,
        height: '14px',
        overflowX: 'auto',
        overflowY: 'hidden',
        zIndex: 5,
        background: '#f3f3f3',
        borderTop: '1px solid #ccc',
        pointerEvents: 'all',
      }}
      className="nodrag nopan"
    >
      <div style={{ width: `${VIRTUAL_WIDTH}px`, height: '1px' }} />
    </div>
  );
}

function SyncVerticalScrollbar() {
  const { x, y, zoom } = useViewport();
  const { setViewport } = useReactFlow();
  const scrollContainerRef = useRef(null);
  const isSyncingFromFlow = useRef(false);
  const isSyncingFromScroll = useRef(false);
  
  const VIRTUAL_HEIGHT = 5000;
  
  useEffect(() => {
    if (isSyncingFromScroll.current) {
      isSyncingFromScroll.current = false;
      return;
    }
    if (scrollContainerRef.current) {
      isSyncingFromFlow.current = true;
      scrollContainerRef.current.scrollTop = -y + (VIRTUAL_HEIGHT / 2);
    }
  }, [y]);

  const onScroll = (e) => {
    if (isSyncingFromFlow.current) {
      isSyncingFromFlow.current = false;
      return;
    }
    isSyncingFromScroll.current = true;
    const newY = -(e.target.scrollTop - (VIRTUAL_HEIGHT / 2));
    setViewport({ x, y: newY, zoom });
  };

  return (
    <div
      ref={scrollContainerRef}
      onScroll={onScroll}
      style={{
        position: 'absolute',
        top: 0,
        bottom: 39,
        right: 0,
        width: '14px',
        overflowY: 'auto',
        overflowX: 'hidden',
        zIndex: 5,
        background: '#f3f3f3',
        borderLeft: '1px solid #ccc',
        pointerEvents: 'all',
      }}
      className="nodrag nopan"
    >
      <div style={{ height: `${VIRTUAL_HEIGHT}px`, width: '1px' }} />
    </div>
  );
}

const nodeTypes = { classNode: ClassNode };
const edgeTypes = { umlEdge: UMLEdge };

const VISIBILITIES = [
  { value: '+', label: '+ Public' },
  { value: '-', label: '- Private' },
  { value: '#', label: '# Protected' },
  { value: '~', label: '~ Package' },
];

// Tipos de relación UML 2.5 — 5 tipos estándar
const RELATION_TYPES = [
  { value: 'association',  label: 'Asociación',   symbol: '—',   color: '#334155' },
  { value: 'dependency',   label: 'Dependencia',  symbol: '⤳',   color: '#d97706' },
  { value: 'aggregation',  label: 'Agregación',   symbol: '◇—',  color: '#0284c7' },
  { value: 'composition',  label: 'Composición',  symbol: '◆—',  color: '#0f172a' },
  { value: 'inheritance',  label: 'Herencia',     symbol: '▷',   color: '#2563eb' },
];

function DiagramPageInner() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { currentProject, getProject, deleteProject } = useProjectStore();
  const { fitView, screenToFlowPosition } = useReactFlow();

  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [loading, setLoading]           = useState(true);
  const [showCollabModal, setShowCollabModal] = useState(false);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [showAIPanel, setShowAIPanel] = useState(false);
  const [showImageModal, setShowImageModal] = useState(false);
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedRelType, setSelectedRelType] = useState('select');
  const [connectingSourceId, setConnectingSourceId] = useState(null);
  // Ref para evitar stale closure en onConnect
  const selectedRelTypeRef = useRef('select');
  // Ref para ignorar actualizaciones remotas mientras guardamos localmente
  const isApplyingRemote = useRef(false);


  // Sincronizar propiedades visuales de los nodos para evitar render inline
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => {
        const relationMode = !!selectedRelType && selectedRelType !== 'select';
        const isConnecting = connectingSourceId === n.id;
        
        if (n.data?.isRelationMode === relationMode && n.data?.isConnectingSource === isConnecting) {
          return n;
        }
        
        return {
          ...n,
          data: {
            ...n.data,
            isRelationMode: relationMode,
            isConnectingSource: isConnecting,
          },
        };
      })
    );
  }, [selectedRelType, connectingSourceId, setNodes]);

  // Formularios
  const [newAttr,    setNewAttr]    = useState({ name: '', data_type: 'String', visibility: '-' });
  const [newMethod,  setNewMethod]  = useState({ name: '', return_type: 'void', visibility: '+' });
  const [editingName, setEditingName] = useState('');
  const [savingName,  setSavingName]  = useState(false);

  // Edición inline de atributos y métodos
  const [editingAttrId, setEditingAttrId] = useState(null);
  const [editingAttrData, setEditingAttrData] = useState({ name: '', data_type: 'String', visibility: '-' });
  const [editingMethodId, setEditingMethodId] = useState(null);
  const [editingMethodData, setEditingMethodData] = useState({ name: '', return_type: 'void', visibility: '+' });

  // Estado para arrastrar atributos y métodos
  const [dragAttrIdx,   setDragAttrIdx]   = useState(null);
  const [dragMethodIdx, setDragMethodIdx] = useState(null);
  // Estado del edge seleccionado (para editar tipo, multiplicidad, etc.)
  const [selectedEdge, setSelectedEdge] = useState(null);
  const [edgeSrcMult,  setEdgeSrcMult]  = useState('');
  const [edgeTgtMult,  setEdgeTgtMult]  = useState('');
  const [edgeRelType,  setEdgeRelType]  = useState('association');
  const [edgeLabel,    setEdgeLabel]    = useState('');  // texto libre: "TIENE", "IS A", etc.
  // Mostrar / ocultar tipo de dato en atributos de la clase seleccionada
  const [showDataTypes, setShowDataTypes] = useState(true);
  // Ref para el contenedor del canvas (para calcular coordenadas de cursor)
  const canvasRef = useRef(null);




  // ── Guardar diagrama en PostgreSQL (columna datos_diagrama) ─────────────────
  const saveDiagram = useCallback(async (currentNodes = nodes, currentEdges = edges) => {
    try {
      const sanitizedNodes = (currentNodes || []).map(n => ({
        ...n,
        dragging: false,
        selected: false,
      }));
      const sanitizedEdges = (currentEdges || []).map(e => ({
        ...e,
        selected: false,
      }));
      await api.post(`projects/${id}/diagram/`, {
        nodes: sanitizedNodes,
        edges: sanitizedEdges,
      });
      return true;
    } catch {
      toast.error('Error al sincronizar con PostgreSQL');
      return false;
    }
  }, [id, nodes, edges]);

  // ── Colaboración en tiempo real ───────────────────────────────────────────
  const handleRemoteUpdate = useCallback(({ nodes: remoteNodes, edges: remoteEdges }) => {
    // Aplicar el estado del diagrama recibido de otro colaborador
    isApplyingRemote.current = true;
    const sanitizedNodes = (remoteNodes || []).map(n => ({
      ...n,
      dragging: false,
      selected: false,
    }));
    setNodes(sanitizedNodes);
    setEdges((remoteEdges || []).map(e => ({ ...e, reconnectable: true, selected: false })));
    // Pequeño delay para volver a permitir envíos locales
    setTimeout(() => { isApplyingRemote.current = false; }, 100);
  }, [setNodes, setEdges]);

  const { wsStatus, collaborators, sendDiagramUpdate, sendCursorMove } = useCollaboration({
    diagramId: id,
    nodes,
    edges,
    onRemoteUpdate: handleRemoteUpdate,
    enabled: !loading,
  });

  // Refs para siempre tener acceso al estado más reciente sin depender de closures (cierres de estado)
  const nodesRef = useRef(nodes);
  const edgesRef = useRef(edges);
  useEffect(() => {
    nodesRef.current = nodes;
    edgesRef.current = edges;
  }, [nodes, edges]);

  // ── Historial Deshacer (Undo) / Rehacer (Redo) ───────────────────────────
  const undoStackRef = useRef([]);
  const redoStackRef = useRef([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const updateUndoRedoState = useCallback(() => {
    setCanUndo(undoStackRef.current.length > 0);
    setCanRedo(redoStackRef.current.length > 0);
  }, []);

  const takeSnapshot = useCallback(() => {
    try {
      const snapshot = JSON.parse(JSON.stringify({
        nodes: nodesRef.current,
        edges: edgesRef.current,
      }));
      undoStackRef.current.push(snapshot);
      if (undoStackRef.current.length > 50) {
        undoStackRef.current.shift();
      }
      redoStackRef.current = [];
      updateUndoRedoState();
    } catch (err) {
      console.error('Error al tomar snapshot del diagrama:', err);
    }
  }, [updateUndoRedoState]);

  const handleUndo = useCallback(() => {
    if (undoStackRef.current.length === 0) return;

    try {
      const currentSnapshot = JSON.parse(JSON.stringify({
        nodes: nodesRef.current,
        edges: edgesRef.current,
      }));
      redoStackRef.current.push(currentSnapshot);
      if (redoStackRef.current.length > 50) {
        redoStackRef.current.shift();
      }

      const previousSnapshot = undoStackRef.current.pop();
      updateUndoRedoState();

      const restoredNodes = previousSnapshot.nodes || [];
      const restoredEdges = (previousSnapshot.edges || []).map(e => ({ ...e, reconnectable: true }));

      setNodes(restoredNodes);
      setEdges(restoredEdges);

      setSelectedNode(curr => {
        if (!curr) return null;
        const exists = restoredNodes.find(n => n.id === curr.id || n.data?.id === curr.id);
        return exists ? exists.data : null;
      });

      setSelectedEdge(curr => {
        if (!curr) return null;
        return restoredEdges.find(e => e.id === curr.id) || null;
      });

      saveDiagram(restoredNodes, restoredEdges);
      if (!isApplyingRemote.current) sendDiagramUpdate(restoredNodes, restoredEdges);
      toast.success('Deshacer (Ctrl+Z)', { icon: '↩️', duration: 1000 });
    } catch (err) {
      console.error('Error al deshacer:', err);
    }
  }, [updateUndoRedoState, setNodes, setEdges, saveDiagram, sendDiagramUpdate]);

  const handleRedo = useCallback(() => {
    if (redoStackRef.current.length === 0) return;

    try {
      const currentSnapshot = JSON.parse(JSON.stringify({
        nodes: nodesRef.current,
        edges: edgesRef.current,
      }));
      undoStackRef.current.push(currentSnapshot);
      if (undoStackRef.current.length > 50) {
        undoStackRef.current.shift();
      }

      const nextSnapshot = redoStackRef.current.pop();
      updateUndoRedoState();

      const restoredNodes = nextSnapshot.nodes || [];
      const restoredEdges = (nextSnapshot.edges || []).map(e => ({ ...e, reconnectable: true }));

      setNodes(restoredNodes);
      setEdges(restoredEdges);

      setSelectedNode(curr => {
        if (!curr) return null;
        const exists = restoredNodes.find(n => n.id === curr.id || n.data?.id === curr.id);
        return exists ? exists.data : null;
      });

      setSelectedEdge(curr => {
        if (!curr) return null;
        return restoredEdges.find(e => e.id === curr.id) || null;
      });

      saveDiagram(restoredNodes, restoredEdges);
      if (!isApplyingRemote.current) sendDiagramUpdate(restoredNodes, restoredEdges);
      toast.success('Rehacer (Ctrl+Y)', { icon: '↪️', duration: 1000 });
    } catch (err) {
      console.error('Error al rehacer:', err);
    }
  }, [updateUndoRedoState, setNodes, setEdges, saveDiagram, sendDiagramUpdate]);

  // Atajos de teclado globales (Ctrl+Z / Ctrl+Y / Escape) y eventos de snapshot
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Escape para cancelar modo relación y volver a puntero
      if (e.key === 'Escape') {
        setSelectedRelType('select');
        selectedRelTypeRef.current = 'select';
        setConnectingSourceId(null);
        return;
      }

      // Si el foco está en un campo de texto/formulario, no interceptar Ctrl+Z / Ctrl+Y
      const activeEl = document.activeElement;
      const isInputActive = activeEl && (
        activeEl.tagName === 'INPUT' ||
        activeEl.tagName === 'TEXTAREA' ||
        activeEl.tagName === 'SELECT' ||
        activeEl.isContentEditable
      );
      if (isInputActive) return;

      const isCtrlOrCmd = e.ctrlKey || e.metaKey;
      if (!isCtrlOrCmd) return;

      if (e.key === 'z' || e.key === 'Z') {
        e.preventDefault();
        if (!e.shiftKey) {
          handleUndo();
        } else {
          handleRedo();
        }
      } else if (e.key === 'y' || e.key === 'Y') {
        e.preventDefault();
        handleRedo();
      }
    };

    const handleCustomSnapshot = () => {
      takeSnapshot();
    };

    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('take-snapshot', handleCustomSnapshot);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('take-snapshot', handleCustomSnapshot);
    };
  }, [handleUndo, handleRedo, takeSnapshot]);

  const saveTimeoutRef = useRef(null);
  const scheduleSave = useCallback(() => {
    if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
    saveTimeoutRef.current = setTimeout(() => {
      saveDiagram(nodesRef.current, edgesRef.current);
      if (!isApplyingRemote.current) sendDiagramUpdate(nodesRef.current, edgesRef.current);
    }, 150);
  }, [saveDiagram, sendDiagramUpdate]);

  // Escuchar evento de actualización de edge desde UMLEdge.jsx (editor inline)
  useEffect(() => {
    const handleEdgeUpdate = (e) => {
      const { edgeId, newData } = e.detail;
      takeSnapshot();
      setEdges(eds => {
        const updated = eds.map(edge => edge.id === edgeId ? { ...edge, data: { ...edge.data, ...newData } } : edge);
        setTimeout(() => saveDiagram(undefined, updated), 50);
        return updated;
      });
    };
    window.addEventListener('update-edge-data', handleEdgeUpdate);
    window.addEventListener('save-diagram', scheduleSave);
    return () => {
      window.removeEventListener('update-edge-data', handleEdgeUpdate);
      window.removeEventListener('save-diagram', scheduleSave);
    };
  }, [setEdges, saveDiagram, scheduleSave, takeSnapshot]);

  // ── Carga inicial desde PostgreSQL ───────────────────────────────────────────
  useEffect(() => {
    const fetchData = async () => {
      try {
        await getProject(id);
        const res = await api.get(`projects/${id}/diagram/`);

        if (res.data && res.data.nodes) {
          // Normalizar handles antiguos si no tienen sufijo -source / -target
          const normalizedEdges = (res.data.edges || []).map(e => {
            let sh = e.sourceHandle;
            let th = e.targetHandle;
            if (sh && !sh.includes('-')) sh = `${sh}-source`;
            if (th && !th.includes('-')) th = `${th}-target`;
            return { ...e, reconnectable: true, sourceHandle: sh, targetHandle: th, selected: false };
          });
          const cleanNodes = (res.data.nodes || []).map(n => ({ ...n, dragging: false, selected: false }));
          setNodes(cleanNodes);
          setEdges(normalizedEdges);
        } else if (res.data && res.data.classes) {
          // compatibilidad si viene en formato legado
          const initialNodes = res.data.classes.map(cls => ({
            id:       `class-${cls.id}`,
            type:     'classNode',
            position: { x: cls.pos_x, y: cls.pos_y },
            data:     { ...cls },
            selected: false,
          }));
          const initialEdges = (res.data.relations || []).map(rel => ({
            id:            `edge-${rel.id}`,
            type:          'umlEdge',
            reconnectable: true,
            source:        `class-${rel.source}`,
            target:        `class-${rel.target}`,
            data:          { relation_type: rel.relation_type },
            selected:      false,
          }));
          setNodes(initialNodes);
          setEdges(initialEdges);
        } else {
          setNodes([]);
          setEdges([]);
        }
      } catch {
        toast.error('Error al cargar el diagrama');
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [id, getProject, setNodes, setEdges]);

  // ── Cálculo automático de mejores extremos (borde exterior más cercano) ──
  const getOptimalEndpoints = useCallback((sourceNodeId, targetNodeId) => {
    const srcNode = nodes.find(n => n.id === sourceNodeId || n.data?.id === sourceNodeId);
    const tgtNode = nodes.find(n => n.id === targetNodeId || n.data?.id === targetNodeId);

    if (!srcNode || !tgtNode) {
      return { sourceHandle: 'bottom-source', targetHandle: 'top-target' };
    }

    const sx = (srcNode.position?.x ?? 0) + (srcNode.measured?.width || 160) / 2;
    const sy = (srcNode.position?.y ?? 0) + (srcNode.measured?.height || 100) / 2;
    const tx = (tgtNode.position?.x ?? 0) + (tgtNode.measured?.width || 160) / 2;
    const ty = (tgtNode.position?.y ?? 0) + (tgtNode.measured?.height || 100) / 2;

    const dx = tx - sx;
    const dy = ty - sy;

    if (Math.abs(dx) >= Math.abs(dy)) {
      if (dx > 0) {
        return { sourceHandle: 'right-source', targetHandle: 'left-target' };
      } else {
        return { sourceHandle: 'left-source', targetHandle: 'right-target' };
      }
    } else {
      if (dy > 0) {
        return { sourceHandle: 'bottom-source', targetHandle: 'top-target' };
      } else {
        return { sourceHandle: 'top-source', targetHandle: 'bottom-target' };
      }
    }
  }, [nodes]);

  // ── Selección de nodo y Conexión Clic-a-Clic ──────────────────────────────
  const onNodeClick = useCallback((_evt, node) => {
    const isRelMode = selectedRelTypeRef.current && selectedRelTypeRef.current !== 'select';

    if (isRelMode) {
      let relType = selectedRelTypeRef.current;
      if (!relType || relType === 'select') relType = 'association';

      setConnectingSourceId((currentSrc) => {
        if (!currentSrc) {
          // Primer clic: fijar como origen de la relación
          toast(`Clase «${node.data?.name || 'clase'}» seleccionada. Haz clic en la clase destino o jala hacia ella.`, { icon: '🎯', duration: 2500 });
          return node.id;
        } else if (currentSrc === node.id) {
          // Si hace clic en el mismo nodo, deseleccionar
          return null;
        } else {
          // Segundo clic: conectar origen con este nodo destino
          takeSnapshot();
          const optimal = getOptimalEndpoints(currentSrc, node.id);
          const newEdge = {
            id:            `edge-${Date.now()}`,
            type:          'umlEdge',
            source:        currentSrc,
            target:        node.id,
            sourceHandle:  optimal.sourceHandle,
            targetHandle:  optimal.targetHandle,
            reconnectable: true,
            data:          { relation_type: relType, sourceMultiplicity: '', targetMultiplicity: '', bendX: 0, bendY: 0 },
          };
          setEdges(eds => {
            const updated = addEdge(newEdge, eds);
            setTimeout(() => {
              saveDiagram(undefined, updated);
              if (!isApplyingRemote.current) sendDiagramUpdate(nodes, updated);
            }, 50);
            return updated;
          });
          toast.success(`Relación «${relType}» creada`, { icon: '🔗', duration: 1500 });
          return null;
        }
      });
      return;
    }

    // Modo normal de puntero: seleccionar clase para editar propiedades
    // Si no está pulsando tecla modificadora (Ctrl / Cmd / Shift), asegurar que SOLO este nodo quede seleccionado
    const isMultiSelect = _evt?.ctrlKey || _evt?.metaKey || _evt?.shiftKey;
    if (!isMultiSelect) {
      setNodes((prev) =>
        prev.map((n) => ({
          ...n,
          selected: n.id === node.id,
        }))
      );
      setEdges((prev) =>
        prev.map((e) => (e.selected ? { ...e, selected: false } : e))
      );
    }

    setSelectedNode(node.data);
    setSelectedEdge(null);
    setEditingName(node.data.name);
    // Sincronizar el checkbox de tipos de datos con el valor guardado en el nodo
    setShowDataTypes(node.data.showDataTypes !== false);
    setEditingAttrId(null);
    setEditingMethodId(null);
  }, [getOptimalEndpoints, setEdges, saveDiagram, sendDiagramUpdate, nodes, takeSnapshot, setNodes]);

  const onPaneClick = useCallback(() => {
    setSelectedNode(null);
    setSelectedEdge(null);
    setEditingAttrId(null);
    setEditingMethodId(null);
    setConnectingSourceId(null);
    // Deseleccionar todas las clases y relaciones del canvas
    setNodes((prev) => prev.map((n) => (n.selected ? { ...n, selected: false } : n)));
    setEdges((prev) => prev.map((e) => (e.selected ? { ...e, selected: false } : e)));
  }, [setNodes, setEdges]);

  // ── Conectar nodos (crear relación UML al jalar desde el centro o bordes) ──
  const onConnect = useCallback((params) => {
    if (params.source === params.target) {
      toast.error('No puedes conectar una clase consigo misma desde el editor.');
      return;
    }
    takeSnapshot();
    let relType = selectedRelTypeRef.current;
    if (!relType || relType === 'select') relType = 'association';

    // Si la conexión se jaló desde el centro o se soltó en el centro, mapear al borde exterior óptimo
    let sourceHandle = params.sourceHandle;
    let targetHandle = params.targetHandle;

    if (!sourceHandle || sourceHandle.includes('center') || !targetHandle || targetHandle.includes('center')) {
      const optimal = getOptimalEndpoints(params.source, params.target);
      if (!sourceHandle || sourceHandle.includes('center')) sourceHandle = optimal.sourceHandle;
      if (!targetHandle || targetHandle.includes('center')) targetHandle = optimal.targetHandle;
    }

    if (relType === 'association_class') {
      const sourceNode = nodes.find(n => n.id === params.source);
      const targetNode = nodes.find(n => n.id === params.target);
      let midX = 300, midY = 300;
      if (sourceNode && targetNode) {
        midX = (sourceNode.position.x + targetNode.position.x) / 2;
        midY = ((sourceNode.position.y + targetNode.position.y) / 2) + 120;
      }
      
      const newClassId = `class-${Date.now()}`;
      const newNode = {
        id: newClassId,
        type: 'classNode',
        position: { x: midX, y: midY },
        data: {
          id: newClassId,
          name: `AssociationClass`,
          is_abstract: false,
          is_interface: false,
          visibility: 'public',
          attributes: [],
          methods: []
        }
      };

      const edgeMain = {
        ...params,
        sourceHandle,
        targetHandle,
        id: `edge-${Date.now()}-main`,
        type: 'umlEdge',
        reconnectable: true,
        data: { relation_type: 'association', associationClassId: newClassId, sourceMultiplicity: '', targetMultiplicity: '', bendX: 0, bendY: 0 },
      };

      const updatedNodes = [...nodes, newNode];
      const updatedEdges = [...edges, edgeMain];
      
      setNodes(updatedNodes);
      setEdges(updatedEdges);
      
      setTimeout(() => {
        saveDiagram(updatedNodes, updatedEdges);
        if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, updatedEdges);
      }, 50);
      
      setConnectingSourceId(null);
      toast.success('Clase de asociación creada', { icon: '✨', duration: 1500 });
      return;
    }

    const newEdge = {
      ...params,
      sourceHandle,
      targetHandle,
      id:            `edge-${Date.now()}`,
      type:          'umlEdge',
      reconnectable: true,
      data:          { relation_type: relType, sourceMultiplicity: '', targetMultiplicity: '', bendX: 0, bendY: 0 },
    };
    
    const updatedEdgesNormal = [...edges, newEdge];
    setEdges(updatedEdgesNormal);
    
    setTimeout(() => {
      saveDiagram(undefined, updatedEdgesNormal);
      if (!isApplyingRemote.current) sendDiagramUpdate(nodes, updatedEdgesNormal);
    }, 50);
    
    setConnectingSourceId(null);
    toast.success(`Relación «${relType}» creada`, { icon: '🔗', duration: 1500 });
  }, [getOptimalEndpoints, setEdges, setNodes, saveDiagram, sendDiagramUpdate, nodes, edges, takeSnapshot]);

  // ── Reconectar relación UML a otra clase o handle arrastrando sus extremos ──
  const onReconnect = useCallback((oldEdge, newConnection) => {
    if (newConnection.source === newConnection.target) {
      toast.error('No puedes reconectar una relación a la misma clase.');
      return;
    }
    takeSnapshot();
    setEdges((eds) => {
      const nextEdges = reconnectEdge(oldEdge, newConnection, eds, { shouldReplaceId: false });
      // Limpiamos la curvatura previa para trazar una línea recta y limpia hacia la nueva clase
      const updated = nextEdges.map(e =>
        e.id === oldEdge.id
          ? { ...e, reconnectable: true, data: { ...(e.data || {}), bendX: 0, bendY: 0 } }
          : e
      );
      setTimeout(() => {
        saveDiagram(undefined, updated);
        if (!isApplyingRemote.current) sendDiagramUpdate(nodes, updated);
      }, 50);
      return updated;
    });
    setSelectedEdge((current) =>
      current?.id === oldEdge.id
        ? { ...current, ...newConnection, data: { ...(current.data || {}), bendX: 0, bendY: 0 } }
        : current
    );
    toast.success('Relación reconectada exitosamente', { icon: '🔄', duration: 1500 });
  }, [setEdges, saveDiagram, sendDiagramUpdate, nodes, takeSnapshot]);

  // ── Selección y edición de edge ───────────────────────────────────────────────
  const onEdgeClick = useCallback((_evt, edge) => {
    setSelectedNode(null);
    setSelectedEdge(edge);
    setEdgeSrcMult(edge.data?.sourceMultiplicity ?? '');
    setEdgeTgtMult(edge.data?.targetMultiplicity ?? '');
    setEdgeRelType(edge.data?.relation_type ?? 'association');
    setEdgeLabel(edge.data?.label ?? '');
    // Deseleccionar nodos al seleccionar una relación
    setNodes((prev) => prev.map((n) => (n.selected ? { ...n, selected: false } : n)));
  }, [setNodes]);

  // Reconectar extremo desde selector de clase en el panel lateral
  const handleChangeEdgeEndpoint = useCallback((endpointType, newClassId) => {
    if (!selectedEdge || !newClassId) return;
    takeSnapshot();
    const isSource = endpointType === 'source';
    const newHandle = isSource ? 'bottom-source' : 'top-target';

    setEdges(eds => {
      const updated = eds.map(e => {
        if (e.id !== selectedEdge.id) return e;
        return {
          ...e,
          [isSource ? 'source' : 'target']: newClassId,
          [isSource ? 'sourceHandle' : 'targetHandle']: newHandle,
          data: { ...(e.data || {}), bendX: 0, bendY: 0 },
        };
      });
      setTimeout(() => saveDiagram(undefined, updated), 50);
      return updated;
    });

    setSelectedEdge(curr => curr ? {
      ...curr,
      [isSource ? 'source' : 'target']: newClassId,
      [isSource ? 'sourceHandle' : 'targetHandle']: newHandle,
      data: { ...(curr.data || {}), bendX: 0, bendY: 0 },
    } : curr);

    const targetNode = nodes.find(n => n.id === newClassId || n.data?.id === newClassId);
    toast.success(`Relación reconectada a «${targetNode?.data?.name || 'clase'}»`, { icon: '🔄', duration: 1500 });
  }, [selectedEdge, nodes, setEdges, saveDiagram, takeSnapshot]);

  // Aplica cambios de multiplicidad, tipo y label al edge seleccionado
  const applyEdgeChanges = useCallback((overrides = {}) => {
    takeSnapshot();
    setEdges(eds => {
      const updated = eds.map(e => {
        if (e.id !== (overrides.edgeId ?? selectedEdge?.id)) return e;
        return {
          ...e,
          data: {
            ...e.data,
            relation_type:      overrides.relType  ?? edgeRelType,
            sourceMultiplicity: overrides.srcMult  ?? edgeSrcMult,
            targetMultiplicity: overrides.tgtMult  ?? edgeTgtMult,
            label:              overrides.label    ?? edgeLabel,
          },
        };
      });
      setTimeout(() => saveDiagram(undefined, updated), 50);
      return updated;
    });
  }, [selectedEdge, edgeRelType, edgeSrcMult, edgeTgtMult, edgeLabel, setEdges, saveDiagram, takeSnapshot]);

  // Elimina el edge seleccionado
  const handleDeleteEdge = useCallback(() => {
    if (!selectedEdge) return;
    takeSnapshot();
    setEdges(eds => {
      const updated = eds.filter(e => e.id !== selectedEdge.id);
      saveDiagram(nodes, updated);
      return updated;
    });
    setSelectedEdge(null);
    toast.success('Relación eliminada', { icon: '🗑️', duration: 1200 });
  }, [selectedEdge, setEdges, saveDiagram, nodes, takeSnapshot]);


  // ── Sincronizar eliminaciones de teclado con el backend ──
  const onNodesDelete = useCallback(() => {
    scheduleSave();
  }, [scheduleSave]);

  const onEdgesDelete = useCallback(() => {
    scheduleSave();
  }, [scheduleSave]);

  // ── CRUD Clases ──────────────────────────────────────────────────────────────
  const handleAddClass = (options = {}) => {
    takeSnapshot();
    const newId = `class-${Date.now()}`;
    const isInterface = !!options?.is_interface;
    const newClassData = {
      id:          newId,
      name:        isInterface ? `Interface${nodes.length + 1}` : `Class${nodes.length + 1}`,
      is_abstract: !!options?.is_abstract,
      is_interface: isInterface,
      attributes:  [],
      methods:     [],
    };
    const newNode = {
      id:       newId,
      type:     'classNode',
      position: { x: 220 + ((nodes.length * 35) % 200), y: 140 + ((nodes.length * 25) % 180) },
      data:     newClassData,
      selected: true,
    };
    // Deseleccionar las demás clases para que la nueva sea la única seleccionada
    const updatedNodes = [...nodes.map((n) => ({ ...n, selected: false })), newNode];
    setNodes(updatedNodes);
    setSelectedNode(newClassData);
    setSelectedEdge(null);
    setEditingName(newClassData.name);
    saveDiagram(updatedNodes, edges);
    if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, edges);
    toast.success(isInterface ? 'Interfaz añadida' : 'Clase añadida');
  };

  const handleDeleteClass = () => {
    if (!selectedNode) return;
    if (!window.confirm(`¿Eliminar la clase "${selectedNode.name}"?`)) return;
    takeSnapshot();

    const targetId = selectedNode.id;
    const updatedNodes = nodes.filter(n => n.id !== targetId && n.data?.id !== targetId);
    const updatedEdges = edges.filter(
      e => e.source !== targetId && e.target !== targetId &&
           e.source !== `class-${targetId}` && e.target !== `class-${targetId}`
    );
    setNodes(updatedNodes);
    setEdges(updatedEdges);
    setSelectedNode(null);
    saveDiagram(updatedNodes, updatedEdges);
    toast.success('Clase eliminada');
  };

  const handleSaveName = () => {
    if (!selectedNode || !editingName.trim()) return;
    takeSnapshot();
    setSavingName(true);
    const targetId = selectedNode.id;
    const updatedNodeData = { ...selectedNode, name: editingName.trim() };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, name: editingName.trim() } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    saveDiagram(updatedNodes, edges);
    setSavingName(false);
    toast.success('Nombre actualizado');
  };

  const handleToggleAbstract = () => {
    if (!selectedNode) return;
    takeSnapshot();
    const targetId = selectedNode.id;
    const isAbs = !selectedNode.is_abstract;
    const updatedNodeData = { ...selectedNode, is_abstract: isAbs };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, is_abstract: isAbs } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    saveDiagram(updatedNodes, edges);
  };

  // ── Atributos ────────────────────────────────────────────────────────────────
  const handleAddAttr = () => {
    if (!selectedNode || !newAttr.name.trim()) return;
    takeSnapshot();
    const targetId = selectedNode.id;
    const attrObj = { id: `attr-${Date.now()}`, ...newAttr };
    const updatedAttrs = [...(selectedNode.attributes || []), attrObj];
    const updatedNodeData = { ...selectedNode, attributes: updatedAttrs };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, attributes: updatedAttrs } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    setNewAttr({ name: '', data_type: 'String', visibility: '-' });
    saveDiagram(updatedNodes, edges);
    if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, edges);
    toast.success('Atributo añadido');
  };

  const handleStartEditAttr = (attr) => {
    setEditingAttrId(attr.id);
    setEditingAttrData({
      name: attr.name || '',
      data_type: attr.data_type || 'String',
      visibility: attr.visibility || '-',
    });
  };

  const handleCancelEditAttr = () => {
    setEditingAttrId(null);
    setEditingAttrData({ name: '', data_type: 'String', visibility: '-' });
  };

  const handleSaveEditAttr = (attrId) => {
    const idToEdit = attrId || editingAttrId;
    if (!selectedNode || !idToEdit) return;
    if (!editingAttrData.name.trim()) {
      toast.error('El nombre del atributo no puede estar vacío');
      return;
    }
    takeSnapshot();
    const targetId = selectedNode.id;
    const updatedAttrs = (selectedNode.attributes || []).map(a =>
      a.id === idToEdit
        ? {
            ...a,
            name: editingAttrData.name.trim(),
            data_type: editingAttrData.data_type.trim() || 'String',
            visibility: editingAttrData.visibility || '-',
          }
        : a
    );
    const updatedNodeData = { ...selectedNode, attributes: updatedAttrs };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, attributes: updatedAttrs } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    saveDiagram(updatedNodes, edges);
    if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, edges);
    setEditingAttrId(null);
    toast.success('Atributo actualizado');
  };

  const handleDeleteAttr = (attrId) => {
    if (!selectedNode) return;
    takeSnapshot();
    const targetId = selectedNode.id;
    const updatedAttrs = (selectedNode.attributes || []).filter(a => a.id !== attrId);
    const updatedNodeData = { ...selectedNode, attributes: updatedAttrs };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, attributes: updatedAttrs } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    saveDiagram(updatedNodes, edges);
    if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, edges);
    if (editingAttrId === attrId) setEditingAttrId(null);
    toast.success('Atributo eliminado');
  };

  // ── Métodos ──────────────────────────────────────────────────────────────────
  const handleAddMethod = () => {
    if (!selectedNode || !newMethod.name.trim()) return;
    takeSnapshot();
    const targetId = selectedNode.id;
    const methodObj = { id: `method-${Date.now()}`, ...newMethod, parameters: [] };
    const updatedMethods = [...(selectedNode.methods || []), methodObj];
    const updatedNodeData = { ...selectedNode, methods: updatedMethods };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, methods: updatedMethods } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    setNewMethod({ name: '', return_type: 'void', visibility: '+' });
    saveDiagram(updatedNodes, edges);
    if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, edges);
    toast.success('Método añadido');
  };

  const handleStartEditMethod = (meth) => {
    setEditingMethodId(meth.id);
    setEditingMethodData({
      name: meth.name || '',
      return_type: meth.return_type || 'void',
      visibility: meth.visibility || '+',
    });
  };

  const handleCancelEditMethod = () => {
    setEditingMethodId(null);
    setEditingMethodData({ name: '', return_type: 'void', visibility: '+' });
  };

  const handleSaveEditMethod = (methodId) => {
    const idToEdit = methodId || editingMethodId;
    if (!selectedNode || !idToEdit) return;
    if (!editingMethodData.name.trim()) {
      toast.error('El nombre del método no puede estar vacío');
      return;
    }
    takeSnapshot();
    const targetId = selectedNode.id;
    const updatedMethods = (selectedNode.methods || []).map(m =>
      m.id === idToEdit
        ? {
            ...m,
            name: editingMethodData.name.trim(),
            return_type: editingMethodData.return_type.trim() || 'void',
            visibility: editingMethodData.visibility || '+',
          }
        : m
    );
    const updatedNodeData = { ...selectedNode, methods: updatedMethods };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, methods: updatedMethods } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    saveDiagram(updatedNodes, edges);
    if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, edges);
    setEditingMethodId(null);
    toast.success('Método actualizado');
  };

  const handleDeleteMethod = (methodId) => {
    if (!selectedNode) return;
    takeSnapshot();
    const targetId = selectedNode.id;
    const updatedMethods = (selectedNode.methods || []).filter(m => m.id !== methodId);
    const updatedNodeData = { ...selectedNode, methods: updatedMethods };
    const updatedNodes = nodes.map(n =>
      n.id === targetId || n.data?.id === targetId
        ? { ...n, data: { ...n.data, methods: updatedMethods } }
        : n
    );
    setNodes(updatedNodes);
    setSelectedNode(updatedNodeData);
    saveDiagram(updatedNodes, edges);
    if (!isApplyingRemote.current) sendDiagramUpdate(updatedNodes, edges);
    if (editingMethodId === methodId) setEditingMethodId(null);
    toast.success('Método eliminado');
  };

  // ── Guardar en PostgreSQL manual ─────────────────────────────────────────────
  const handleSavePositions = async () => {
    const t = toast.loading('Guardando en PostgreSQL...');
    try {
      await saveDiagram(nodes, edges);
      toast.success('Diagrama guardado en PostgreSQL (PARCIAL_SW1)', { id: t });
    } catch {
      toast.error('Error al guardar', { id: t });
    }
  };

  // ── CU-07: Exportar diagrama como PNG ────────────────────────────────────────
  const handleExportPNG = useCallback(() => {
    const imageWidth  = 1920;
    const imageHeight = 1080;
    const nodesBounds = getNodesBounds(nodes);
    const viewport    = getViewportForBounds(nodesBounds, imageWidth, imageHeight, 0.5, 2, 0.1);

    const viewportEl = document.querySelector('.react-flow__viewport');
    if (!viewportEl) {
      toast.error('No se pudo capturar el canvas');
      return;
    }

    const t = toast.loading('Exportando imagen...');
    toPng(viewportEl, {
      backgroundColor: '#ffffff',
      width: imageWidth,
      height: imageHeight,
      style: {
        width:  imageWidth  + 'px',
        height: imageHeight + 'px',
        transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
        transformOrigin: 'top left',
      },
    })
      .then((dataUrl) => {
        const a = document.createElement('a');
        a.setAttribute('download', `${currentProject?.name || 'diagrama'}.png`);
        a.setAttribute('href', dataUrl);
        a.click();
        toast.success('Imagen exportada correctamente', { id: t, icon: '🖼️' });
      })
      .catch(() => {
        toast.error('Error al exportar la imagen', { id: t });
      });
  }, [nodes, currentProject]);

  // ── CU-08: Exportar e Importar XMI ──────────────────────────────────────────
  const handleExportXMI = useCallback(async () => {
    if (!currentProject) return;
    const t = toast.loading('Exportando XMI...');
    try {
      const res = await api.get(`projects/${currentProject.id}/export-xmi/`, { responseType: 'blob' });
      const blob = new Blob([res.data], { type: 'application/xml' });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = `${currentProject.name.replace(/\s+/g, '_')}.xmi`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
      toast.success('XMI exportado correctamente', { id: t, icon: '⬇️' });
    } catch {
      toast.error('Error al exportar XMI', { id: t });
    }
  }, [currentProject]);

  const handleImportXMI = useCallback(async (e) => {
    if (!currentProject) return;
    const file = e.target.files?.[0];
    if (!file) return;
    
    const formData = new FormData();
    formData.append('file', file);
    
    const t = toast.loading('Importando archivo XMI...');
    try {
      const res = await api.post(`projects/${currentProject.id}/import-xmi/`, formData);
      if (res.data && res.data.diagram) {
        takeSnapshot();
        const newNodes = res.data.diagram.nodes || [];
        const newEdges = (res.data.diagram.edges || []).map(edge => ({ ...edge, reconnectable: true }));
        setNodes(newNodes);
        setEdges(newEdges);
        if (!isApplyingRemote.current) sendDiagramUpdate(newNodes, newEdges);
        setTimeout(() => fitView && fitView({ padding: 0.2, duration: 400 }), 150);
        toast.success('Diagrama XMI importado', { id: t, icon: '⬆️' });
      }
    } catch (err) {
      console.error('Error al importar archivo XMI:', err);
      const msg = err.response?.data?.detail || err.message || 'Error al importar archivo XMI';
      toast.error(msg, { id: t });
    }
    // reset input
    e.target.value = null;
  }, [currentProject, setNodes, setEdges, sendDiagramUpdate, fitView, takeSnapshot]);

  // ── CU-10: Aplicar diagrama generado desde imagen al canvas ───────────────
  const handleApplyVisionDiagram = useCallback((visionNodes, visionEdges) => {
    takeSnapshot();
    setNodes(prev => {
      const updated = [...prev, ...visionNodes];
      saveDiagram(updated, [...edges, ...visionEdges]);
      if (!isApplyingRemote.current) sendDiagramUpdate(updated, [...edges, ...visionEdges]);
      return updated;
    });
    setEdges(prev => [...prev, ...visionEdges]);
  }, [setNodes, setEdges, saveDiagram, edges, sendDiagramUpdate, takeSnapshot]);

  // ── Aplicar actualizaciones de la IA desde el Chat ─────────────────────────
  const handleApplyAIUpdates = useCallback((updates) => {
    if (!updates || updates.length === 0) return;
    takeSnapshot();

    let currentNodes = [...nodes];
    let currentEdges = [...edges];
    let hasChanges = false;

    updates.forEach(update => {
      if (update.action === 'add_class') {
        const nodeId = `class-ai-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
        // Posicionar en el centro de la vista
        const viewportEl = document.querySelector('.react-flow__viewport');
        let x = 300, y = 200;
        if (viewportEl) {
           const transform = viewportEl.style.transform;
           const match = /translate\(([^p]+)px,\s*([^p]+)px\)\s*scale\(([^)]+)\)/.exec(transform);
           if (match) {
             const scale = parseFloat(match[3]);
             const tx = parseFloat(match[1]);
             const ty = parseFloat(match[2]);
             const canvasCenter = document.querySelector('.react-flow').getBoundingClientRect();
             x = (canvasCenter.width / 2 - tx) / scale;
             y = (canvasCenter.height / 2 - ty) / scale;
           }
        }
        currentNodes.push({
          id: nodeId,
          type: 'classNode',
          position: { x: x + (Math.random() * 100 - 50), y: y + (Math.random() * 100 - 50) },
          data: {
            id: nodeId,
            name: update.name || 'NuevaClase',
            is_abstract: false,
            attributes: [],
            methods: [],
          }
        });
        hasChanges = true;
      }
      else if (update.action === 'add_attribute') {
        const nodeIndex = currentNodes.findIndex(n => n.data.name.toLowerCase() === (update.class_name || '').toLowerCase());
        if (nodeIndex !== -1) {
          const targetNode = currentNodes[nodeIndex];
          const newAttr = {
            id: `attr-ai-${Date.now()}-${Math.floor(Math.random() * 1000)}`,
            name: update.attr_name || 'nuevoAtributo',
            data_type: update.data_type || 'String',
            visibility: update.visibility || '-',
          };
          currentNodes[nodeIndex] = {
            ...targetNode,
            data: {
              ...targetNode.data,
              attributes: [...(targetNode.data.attributes || []), newAttr]
            }
          };
          hasChanges = true;
        }
      }
      else if (update.action === 'add_relation') {
        const srcNode = currentNodes.find(n => n.data.name.toLowerCase() === (update.source_class || '').toLowerCase());
        const tgtNode = currentNodes.find(n => n.data.name.toLowerCase() === (update.target_class || '').toLowerCase());
        
        if (srcNode && tgtNode) {
          const edgeId = `edge-ai-${srcNode.id}-${tgtNode.id}-${Date.now()}`;
          currentEdges.push({
            id: edgeId,
            type: 'umlEdge',
            source: srcNode.id,
            target: tgtNode.id,
            reconnectable: true,
            sourceHandle: 'bottom-source',
            targetHandle: 'top-target',
            data: {
              relation_type: update.relation_type || 'association',
              sourceMultiplicity: '',
              targetMultiplicity: '',
            }
          });
          hasChanges = true;
        }
      }
      else if (update.action === 'delete_class') {
        const nodeIndex = currentNodes.findIndex(n => n.data.name.toLowerCase() === (update.name || '').toLowerCase());
        if (nodeIndex !== -1) {
          const removedNodeId = currentNodes[nodeIndex].id;
          currentNodes.splice(nodeIndex, 1);
          currentEdges = currentEdges.filter(e => e.source !== removedNodeId && e.target !== removedNodeId);
          hasChanges = true;
        }
      }
      else if (update.action === 'delete_attribute') {
        const nodeIndex = currentNodes.findIndex(n => n.data.name.toLowerCase() === (update.class_name || '').toLowerCase());
        if (nodeIndex !== -1) {
          const targetNode = currentNodes[nodeIndex];
          currentNodes[nodeIndex] = {
            ...targetNode,
            data: {
              ...targetNode.data,
              attributes: (targetNode.data.attributes || []).filter(a => a.name.toLowerCase() !== (update.attr_name || '').toLowerCase())
            }
          };
          hasChanges = true;
        }
      }
      else if (update.action === 'delete_relation') {
        const srcNode = currentNodes.find(n => n.data.name.toLowerCase() === (update.source_class || '').toLowerCase());
        const tgtNode = currentNodes.find(n => n.data.name.toLowerCase() === (update.target_class || '').toLowerCase());
        if (srcNode && tgtNode) {
          const beforeCount = currentEdges.length;
          // Eliminar la relación en ambas direcciones (por si la IA invierte origen y destino)
          currentEdges = currentEdges.filter(e => !(
            (e.source === srcNode.id && e.target === tgtNode.id) ||
            (e.source === tgtNode.id && e.target === srcNode.id)
          ));
          if (currentEdges.length !== beforeCount) hasChanges = true;
        }
      }
    });

    if (hasChanges) {
      setNodes(currentNodes);
      setEdges(currentEdges);
      saveDiagram(currentNodes, currentEdges);
      if (!isApplyingRemote.current) sendDiagramUpdate(currentNodes, currentEdges);
      toast.success('Diagrama actualizado por la IA');
    }
  }, [nodes, edges, setNodes, setEdges, saveDiagram, sendDiagramUpdate, takeSnapshot]);

  // ── CU-08: Restaurar snapshot ─────────────────────────────────────────────────
  const handleRestoreSnapshot = useCallback((diagramData) => {
    takeSnapshot();
    const restoredNodes = (diagramData.nodes || []);
    const restoredEdges = (diagramData.edges || []).map(e => ({ ...e, reconnectable: true }));
    setNodes(restoredNodes);
    setEdges(restoredEdges);
    toast.success('Diagrama restaurado en el canvas', { icon: '🕐', duration: 3000 });
  }, [setNodes, setEdges, takeSnapshot]);

  const handleDeleteProject = useCallback(async () => {
    if (!currentProject) return;
    if (window.confirm(`¿Estás seguro de que deseas eliminar el proyecto "${currentProject.name}"?\nSe borrarán permanentemente el diagrama, todas sus clases y relaciones.`)) {
      try {
        await deleteProject(currentProject.id);
        toast.success('Proyecto eliminado correctamente');
        navigate('/');
      } catch {
        toast.error('Error al eliminar el proyecto');
      }
    }
  }, [currentProject, deleteProject, navigate]);

  if (loading) return (
    <div style={{ padding: '20px', color: 'var(--text-muted)' }}>Cargando diagrama...</div>
  );

  return (
    <div className="app-container">
      {/* Marcadores UML SVG (invisibles, globales) */}
      <UMLMarkers />

      {/* ── Barra de Menús y Herramientas estilo StarUML ── */}
      <StarUMLMenuBar
        projectName={currentProject?.name || 'Main — Model'}
        user={user}
        onBack={() => navigate('/')}
        onSave={handleSavePositions}
        onUndo={handleUndo}
        onRedo={handleRedo}
        canUndo={canUndo}
        canRedo={canRedo}
        onExportPNG={handleExportPNG}
        onOpenHistory={() => setShowHistoryModal(true)}
        onOpenAssistant={() => setShowAIPanel(true)}
        onOpenImageToUML={() => setShowImageModal(true)}
        onOpenGenerate={() => setShowGenerateModal(true)}
        onOpenCollab={() => setShowCollabModal(true)}
        onExportXMI={handleExportXMI}
        onImportXMI={handleImportXMI}
        onDeleteProject={handleDeleteProject}
        onAddClass={handleAddClass}
        onFitView={() => fitView && fitView({ padding: 0.2, duration: 400 })}
        collaboratorsCount={currentProject?.collaborators?.length || 0}
        isOwner={currentProject?.is_owner}
      />

      {/* ── Área Principal de Diagramado (Toolbox + Canvas + Inspector) ── */}
      <div className="diagram-container" style={{ display: 'flex', flex: 1, position: 'relative', overflow: 'hidden' }}>

        {/* Paleta Lateral Izquierda (Working Diagrams + Toolbox) */}
        <StarUMLToolbox
          selectedRelType={selectedRelType}
          onSelectRelType={(type) => {
            setSelectedRelType(type);
            selectedRelTypeRef.current = type;
          }}
          onAddClass={handleAddClass}
          onAddInterface={() => handleAddClass({ is_interface: true })}
          projectName={currentProject?.name || 'Main'}
        />

        {/* Canvas React Flow — Papel Milimetrado */}
        <div
          ref={canvasRef}
          style={{ flex: 1, height: '100%', background: '#ffffff', position: 'relative' }}
          onMouseMove={(e) => {
            if (!canvasRef.current) return;
            const flowPos = screenToFlowPosition({ x: e.clientX, y: e.clientY });
            sendCursorMove(flowPos.x, flowPos.y, '#007acc');
          }}
        >
          {/* ── Banner Flotante de Modo Relación Activo ── */}
          {selectedRelType && selectedRelType !== 'select' && (
            <div
              style={{
                position: 'absolute',
                top: '12px',
                left: '50%',
                transform: 'translateX(-50%)',
                zIndex: 30,
                background: 'rgba(30, 30, 30, 0.94)',
                backdropFilter: 'blur(6px)',
                color: '#ffffff',
                border: '1px solid #007acc',
                boxShadow: '0 4px 14px rgba(0, 0, 0, 0.4)',
                borderRadius: '20px',
                padding: '5px 16px',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                fontSize: '11.5px',
                userSelect: 'none',
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                <span
                  style={{
                    width: '7px',
                    height: '7px',
                    borderRadius: '50%',
                    background: '#007acc',
                    boxShadow: '0 0 6px #007acc',
                  }}
                />
                <span>Relación:</span>
                <strong style={{ color: '#569cd6' }}>
                  {RELATION_TYPES.find((r) => r.value === selectedRelType)?.label || selectedRelType}
                </strong>
              </span>

              <span style={{ color: '#666666' }}>|</span>

              <span style={{ color: '#cccccc' }}>
                {connectingSourceId
                  ? '🎯 Haz clic en la clase destino'
                  : '✨ Jala desde cualquier parte de una clase hacia otra'}
              </span>

              <button
                onClick={() => {
                  setSelectedRelType('select');
                  selectedRelTypeRef.current = 'select';
                  setConnectingSourceId(null);
                }}
                style={{
                  background: '#333333',
                  color: '#eeeeee',
                  border: '1px solid #444444',
                  borderRadius: '12px',
                  padding: '2px 9px',
                  fontSize: '10.5px',
                  cursor: 'pointer',
                  transition: 'background 0.1s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.background = '#454545')}
                onMouseLeave={(e) => (e.currentTarget.style.background = '#333333')}
                title="Volver a modo selección (Esc)"
              >
                Cancelar (Esc)
              </button>
            </div>
          )}

          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodesDelete={onNodesDelete}
            onEdgesDelete={onEdgesDelete}
            onConnect={onConnect}
            onReconnect={onReconnect}
            edgesReconnectable={true}
            reconnectRadius={30}
            connectionRadius={85}
            connectionLineStyle={{ stroke: '#007acc', strokeWidth: 2 }}
            onNodeClick={onNodeClick}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            onNodeDragStart={() => takeSnapshot()}
            onBeforeDelete={async () => {
              takeSnapshot();
              return true;
            }}
            onNodeDragStop={() => {
              saveDiagram(nodes, edges);
              if (!isApplyingRemote.current) sendDiagramUpdate(nodes, edges);
            }}
            nodeTypes={nodeTypes}
            edgeTypes={edgeTypes}
            connectionMode="loose"
            deleteKeyCode="Delete"
            panOnDrag={false}
            panOnScroll={true}
            selectionOnDrag={true}
            selectionMode={SelectionMode.Partial}
            fitView
            colorMode="light"
            style={{
              background: '#ffffff',
              cursor: selectedRelType && selectedRelType !== 'select' ? 'crosshair' : 'default',
            }}
          >
            {/* Cuadrícula de papel milimetrado clásica de StarUML */}
            <Background variant="lines" color="#e4e4e4" gap={18} size={1} />
            <Controls
              style={{
                background: '#ffffff',
                border: '1px solid #777777',
                borderRadius: '0px',
                boxShadow: '1px 1px 3px rgba(0,0,0,0.2)',
                marginBottom: '28px',
              }}
            />
            {/* MiniMap estilo StarUML en esquina inferior derecha */}
            <MiniMap
              style={{
                background: '#ffffff',
                border: '1px solid #777777',
                borderRadius: '0px',
                width: 140,
                height: 90,
                position: 'absolute',
                right: 12,
                bottom: 30,
              }}
              nodeColor="#333333"
              maskColor="rgba(0,0,0,0.06)"
            />
            {/* Custom Scrollbars */}
            <SyncHorizontalScrollbar />
            <SyncVerticalScrollbar />
          </ReactFlow>

          {/* Cursores de colaboradores en tiempo real */}
          <CollaboratorCursors collaborators={collaborators} />

          {/* Barra de estado de colaboración */}
          <CollabStatus wsStatus={wsStatus} collaborators={collaborators} />

          {/* Barra de estado inferior clásica de StarUML */}
          <div
            style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              right: 0,
              height: '22px',
              background: '#282828',
              borderTop: '1px solid #383838',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '0 8px',
              fontSize: '11px',
              color: '#cccccc',
              fontFamily: 'Segoe UI, Arial, sans-serif',
              userSelect: 'none',
              zIndex: 15,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ color: '#ffffff', background: '#383838', padding: '1px 6px', fontSize: '10px' }}>
                Diagram Thumbnails
              </span>
              <span style={{ color: '#888888' }}>Main — Model</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px', fontSize: '11px' }}>
              <span style={{ color: '#888888' }}>{nodes.length} clases · {edges.length} relaciones</span>
              <span style={{ color: wsStatus === 'connected' ? '#4ec9b0' : '#e5a700', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: wsStatus === 'connected' ? '#4ec9b0' : '#e5a700' }}></span>
                {wsStatus === 'connected' ? 'Ready' : 'Connecting...'}
              </span>
              <span style={{ color: '#ffffff', fontWeight: 600 }}>100%</span>
            </div>
          </div>
        </div>

        {/* Panel lateral derecho — propiedades */}
        <div className="sidebar-panel">
          {/* ── Estado: Edge seleccionado ── */}
          {!selectedNode && selectedEdge ? (
            <>
              {/* Header */}
              <div style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '14px', marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <h3 style={{ fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    🔗 Relación UML
                  </h3>
                  <button className="btn btn-danger" onClick={handleDeleteEdge} style={{ padding: '4px 8px', fontSize: '11px' }}>
                    <Trash2 size={12} /> Eliminar
                  </button>
                </div>
                
                {/* Guía rápida de interacción */}
                <div style={{
                  background: 'rgba(37,99,235,0.08)',
                  border: '1px solid rgba(37,99,235,0.25)',
                  borderRadius: '6px',
                  padding: '8px 10px',
                  fontSize: '11px',
                  color: '#93c5fd',
                  lineHeight: '1.5',
                }}>
                  <div style={{ marginBottom: '3px' }}>
                    🔄 <strong>Mover a otra clase:</strong> Arrastra el extremo de la línea directamente hacia otra clase o selecciónala abajo.
                  </div>
                  <div>
                    〰️ <strong>Curvar línea:</strong> Arrastra el punto central de la flecha.
                  </div>
                </div>
              </div>

            </>

          ) : !selectedNode ? (
            <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)' }}>
              <p style={{ fontSize: '13px', lineHeight: 1.6 }}>
                Haz clic en una <strong style={{ color: '#e2e8f0' }}>clase</strong> para editar sus propiedades.<br />
                Haz clic en una <strong style={{ color: '#94a3b8' }}>flecha</strong> para editar la relación.<br />
                Arrastra desde un <strong style={{ color: 'var(--primary)' }}>punto azul</strong> para conectar.
              </p>
              <div style={{ marginTop: '20px', fontSize: '11px', textAlign: 'left', color: 'var(--text-muted)' }}>
                <div style={{ marginBottom: '8px', fontWeight: '600' }}>Relaciones UML 2.5:</div>
                {RELATION_TYPES.map(rt => (
                  <div key={rt.value} style={{ display: 'flex', gap: '8px', marginBottom: '4px' }}>
                    <span style={{ color: rt.color, fontFamily: 'monospace', minWidth: '28px' }}>{rt.symbol}</span>
                    <span>{rt.label}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (

            <>
              {/* ── Nombre ── */}
              <div style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginBottom: '16px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <h3 style={{ fontSize: '13px', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Clase</h3>
                  <button className="btn btn-danger" onClick={handleDeleteClass} style={{ padding: '4px 8px', fontSize: '11px' }}>
                    <Trash2 size={12} /> Eliminar
                  </button>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    className="input-field"
                    value={editingName}
                    onChange={e => setEditingName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleSaveName()}
                    style={{ fontSize: '14px', fontWeight: 'bold' }}
                  />
                  <button
                    className="btn btn-primary"
                    onClick={handleSaveName}
                    disabled={savingName}
                    style={{ padding: '8px 12px' }}
                    title="Guardar nombre (Enter)"
                  >
                    <Save size={14} />
                  </button>
                </div>
                {/* Opciones de la clase */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '10px' }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', cursor: 'pointer', color: 'var(--text-muted)' }}>
                    <input type="checkbox" checked={selectedNode.is_abstract} onChange={handleToggleAbstract} style={{ accentColor: 'var(--primary)' }} />
                    Clase abstracta
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', cursor: 'pointer', color: 'var(--text-muted)' }}>
                    <input
                      type="checkbox"
                      checked={showDataTypes}
                      onChange={e => {
                        const show = e.target.checked;
                        setShowDataTypes(show);
                        // Persistir en los datos del nodo para que ClassNode lo refleje
                        const targetId = selectedNode.id;
                        const updatedNodeData = { ...selectedNode, showDataTypes: show };
                        const updatedNodes = nodes.map(n =>
                          n.id === targetId || n.data?.id === targetId
                            ? { ...n, data: { ...n.data, showDataTypes: show } }
                            : n
                        );
                        setNodes(updatedNodes);
                        setSelectedNode(updatedNodeData);
                        saveDiagram(updatedNodes, edges);
                      }}
                      style={{ accentColor: '#06b6d4' }}
                    />
                    Mostrar tipos de datos
                  </label>
                </div>
              </div>

              {/* ── Atributos ── */}
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Atributos ({selectedNode.attributes?.length || 0})
                  <span style={{ fontSize: '10px', marginLeft: '6px', fontWeight: '400', color: '#64748b' }}>⠿ arrastra para reordenar</span>
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '8px' }}>
                  {(selectedNode.attributes || []).map((attr, idx) => (
                    editingAttrId === attr.id ? (
                      <div
                        key={attr.id}
                        style={{
                          background: 'rgba(59, 130, 246, 0.1)',
                          border: '1px solid rgba(59, 130, 246, 0.35)',
                          borderRadius: '8px',
                          padding: '8px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '6px',
                        }}
                      >
                        <div style={{ display: 'flex', gap: '5px' }}>
                          <select
                            value={editingAttrData.visibility}
                            onChange={e => setEditingAttrData(prev => ({ ...prev, visibility: e.target.value }))}
                            className="input-field"
                            style={{ width: '90px', fontSize: '11px', padding: '4px 6px' }}
                          >
                            {VISIBILITIES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                          </select>
                          <input
                            className="input-field"
                            placeholder="Nombre del atributo"
                            value={editingAttrData.name}
                            onChange={e => setEditingAttrData(prev => ({ ...prev, name: e.target.value }))}
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleSaveEditAttr(attr.id);
                              if (e.key === 'Escape') handleCancelEditAttr();
                            }}
                            style={{ flex: 1, fontSize: '12px', padding: '4px 8px' }}
                            autoFocus
                          />
                        </div>
                        <div style={{ display: 'flex', gap: '5px' }}>
                          <input
                            className="input-field"
                            placeholder="Tipo de dato (String, Integer, etc.)"
                            value={editingAttrData.data_type}
                            onChange={e => setEditingAttrData(prev => ({ ...prev, data_type: e.target.value }))}
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleSaveEditAttr(attr.id);
                              if (e.key === 'Escape') handleCancelEditAttr();
                            }}
                            style={{ flex: 1, fontSize: '12px', padding: '4px 8px' }}
                          />
                          <button
                            type="button"
                            onClick={() => handleSaveEditAttr(attr.id)}
                            className="btn btn-primary"
                            style={{ padding: '4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                            title="Guardar cambios (Enter)"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={handleCancelEditAttr}
                            className="btn btn-secondary"
                            style={{ padding: '4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                            title="Cancelar (Esc)"
                          >
                            <X size={13} />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        key={attr.id}
                        draggable
                        onDragStart={() => setDragAttrIdx(idx)}
                        onDragOver={e => { e.preventDefault(); }}
                        onDrop={() => {
                          if (dragAttrIdx === null || dragAttrIdx === idx) return;
                          takeSnapshot();
                          const targetId = selectedNode.id;
                          const arr = [...(selectedNode.attributes || [])];
                          const [moved] = arr.splice(dragAttrIdx, 1);
                          arr.splice(idx, 0, moved);
                          const updatedNodeData = { ...selectedNode, attributes: arr };
                          const updatedNodes = nodes.map(n =>
                            n.id === targetId || n.data?.id === targetId
                              ? { ...n, data: { ...n.data, attributes: arr } }
                              : n
                          );
                          setNodes(updatedNodes);
                          setSelectedNode(updatedNodeData);
                          saveDiagram(updatedNodes, edges);
                          setDragAttrIdx(null);
                        }}
                        onDragEnd={() => setDragAttrIdx(null)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '6px',
                          background: dragAttrIdx === idx ? 'rgba(59,130,246,0.12)' : 'rgba(255,255,255,0.04)',
                          borderRadius: '6px',
                          padding: '5px 8px', fontSize: '12px', fontFamily: 'monospace',
                          cursor: 'grab', border: dragAttrIdx === idx ? '1px dashed #3b82f6' : '1px solid transparent',
                          transition: 'background 0.1s',
                        }}
                      >
                        <span style={{ color: '#475569', fontSize: '14px', cursor: 'grab', marginRight: '2px', userSelect: 'none' }} title="Arrastrar para reordenar">⠿</span>
                        <span style={{ color: '#f472b6', minWidth: '12px', fontWeight: 'bold' }}>{attr.visibility}</span>
                        <span
                          style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}
                          onClick={() => handleStartEditAttr(attr)}
                          title="Clic para editar atributo"
                        >
                          {attr.name}: <span style={{ color: '#94a3b8' }}>{attr.data_type}</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => handleStartEditAttr(attr)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#60a5fa', padding: '2px', lineHeight: 1, display: 'flex', alignItems: 'center' }}
                          title="Editar atributo"
                        >
                          <Pencil size={11} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteAttr(attr.id)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '2px', lineHeight: 1, display: 'flex', alignItems: 'center' }}
                          title="Eliminar atributo"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    )
                  ))}
                  {!(selectedNode.attributes?.length) && (
                    <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Sin atributos</p>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <div style={{ display: 'flex', gap: '5px' }}>
                    <select value={newAttr.visibility} onChange={e => setNewAttr(a => ({ ...a, visibility: e.target.value }))} className="input-field" style={{ width: '95px', fontSize: '12px', padding: '5px 6px' }}>
                      {VISIBILITIES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                    </select>
                    <input className="input-field" placeholder="nombre" value={newAttr.name} onChange={e => setNewAttr(a => ({ ...a, name: e.target.value }))} onKeyDown={e => e.key === 'Enter' && handleAddAttr()} style={{ flex: 1, fontSize: '12px', padding: '5px 8px' }} />
                  </div>
                  <div style={{ display: 'flex', gap: '5px' }}>
                    <input className="input-field" placeholder="tipo" value={newAttr.data_type} onChange={e => setNewAttr(a => ({ ...a, data_type: e.target.value }))} style={{ flex: 1, fontSize: '12px', padding: '5px 8px' }} />
                    <button className="btn btn-primary" onClick={handleAddAttr} style={{ padding: '5px 10px' }} title="Agregar atributo"><PlusCircle size={14} /></button>
                  </div>
                </div>
              </div>

              {/* ── Métodos ── */}
              <div>
                <h4 style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Métodos ({selectedNode.methods?.length || 0})
                </h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '8px' }}>
                  {(selectedNode.methods || []).map((meth, idx) => (
                    editingMethodId === meth.id ? (
                      <div
                        key={meth.id}
                        style={{
                          background: 'rgba(16, 185, 129, 0.1)',
                          border: '1px solid rgba(16, 185, 129, 0.35)',
                          borderRadius: '8px',
                          padding: '8px',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '6px',
                        }}
                      >
                        <div style={{ display: 'flex', gap: '5px' }}>
                          <select
                            value={editingMethodData.visibility}
                            onChange={e => setEditingMethodData(prev => ({ ...prev, visibility: e.target.value }))}
                            className="input-field"
                            style={{ width: '90px', fontSize: '11px', padding: '4px 6px' }}
                          >
                            {VISIBILITIES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                          </select>
                          <input
                            className="input-field"
                            placeholder="Nombre del método"
                            value={editingMethodData.name}
                            onChange={e => setEditingMethodData(prev => ({ ...prev, name: e.target.value }))}
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleSaveEditMethod(meth.id);
                              if (e.key === 'Escape') handleCancelEditMethod();
                            }}
                            style={{ flex: 1, fontSize: '12px', padding: '4px 8px' }}
                            autoFocus
                          />
                        </div>
                        <div style={{ display: 'flex', gap: '5px' }}>
                          <input
                            className="input-field"
                            placeholder="Retorno (void, String, etc.)"
                            value={editingMethodData.return_type}
                            onChange={e => setEditingMethodData(prev => ({ ...prev, return_type: e.target.value }))}
                            onKeyDown={e => {
                              if (e.key === 'Enter') handleSaveEditMethod(meth.id);
                              if (e.key === 'Escape') handleCancelEditMethod();
                            }}
                            style={{ flex: 1, fontSize: '12px', padding: '4px 8px' }}
                          />
                          <button
                            type="button"
                            onClick={() => handleSaveEditMethod(meth.id)}
                            className="btn btn-primary"
                            style={{ padding: '4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                            title="Guardar cambios (Enter)"
                          >
                            <Check size={13} />
                          </button>
                          <button
                            type="button"
                            onClick={handleCancelEditMethod}
                            className="btn btn-secondary"
                            style={{ padding: '4px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                            title="Cancelar (Esc)"
                          >
                            <X size={13} />
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div
                        key={meth.id}
                        draggable
                        onDragStart={() => setDragMethodIdx(idx)}
                        onDragOver={e => e.preventDefault()}
                        onDrop={() => {
                          if (dragMethodIdx === null || dragMethodIdx === idx) return;
                          takeSnapshot();
                          const targetId = selectedNode.id;
                          const arr = [...(selectedNode.methods || [])];
                          const [moved] = arr.splice(dragMethodIdx, 1);
                          arr.splice(idx, 0, moved);
                          const updatedNodeData = { ...selectedNode, methods: arr };
                          const updatedNodes = nodes.map(n =>
                            n.id === targetId || n.data?.id === targetId
                              ? { ...n, data: { ...n.data, methods: arr } }
                              : n
                          );
                          setNodes(updatedNodes);
                          setSelectedNode(updatedNodeData);
                          saveDiagram(updatedNodes, edges);
                          setDragMethodIdx(null);
                        }}
                        onDragEnd={() => setDragMethodIdx(null)}
                        style={{
                          display: 'flex', alignItems: 'center', gap: '6px',
                          background: dragMethodIdx === idx ? 'rgba(59,130,246,0.12)' : 'rgba(255,255,255,0.04)',
                          borderRadius: '6px',
                          padding: '5px 8px', fontSize: '12px', fontFamily: 'monospace',
                          cursor: 'grab', border: dragMethodIdx === idx ? '1px dashed #3b82f6' : '1px solid transparent',
                          transition: 'background 0.1s',
                        }}
                      >
                        <span style={{ color: '#475569', fontSize: '14px', cursor: 'grab', marginRight: '2px', userSelect: 'none' }} title="Arrastrar para reordenar">⠿</span>
                        <span style={{ color: '#34d399', minWidth: '12px', fontWeight: 'bold' }}>{meth.visibility}</span>
                        <span
                          style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}
                          onClick={() => handleStartEditMethod(meth)}
                          title="Clic para editar método"
                        >
                          {meth.name}(): <span style={{ color: '#94a3b8' }}>{meth.return_type}</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => handleStartEditMethod(meth)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#60a5fa', padding: '2px', lineHeight: 1, display: 'flex', alignItems: 'center' }}
                          title="Editar método"
                        >
                          <Pencil size={11} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteMethod(meth.id)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '2px', lineHeight: 1, display: 'flex', alignItems: 'center' }}
                          title="Eliminar método"
                        >
                          <Trash2 size={11} />
                        </button>
                      </div>
                    )
                  ))}
                  {!(selectedNode.methods?.length) && (
                    <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Sin métodos</p>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  <div style={{ display: 'flex', gap: '5px' }}>
                    <select value={newMethod.visibility} onChange={e => setNewMethod(m => ({ ...m, visibility: e.target.value }))} className="input-field" style={{ width: '95px', fontSize: '12px', padding: '5px 6px' }}>
                      {VISIBILITIES.map(v => <option key={v.value} value={v.value}>{v.label}</option>)}
                    </select>
                    <input className="input-field" placeholder="nombre" value={newMethod.name} onChange={e => setNewMethod(m => ({ ...m, name: e.target.value }))} onKeyDown={e => e.key === 'Enter' && handleAddMethod()} style={{ flex: 1, fontSize: '12px', padding: '5px 8px' }} />
                  </div>
                  <div style={{ display: 'flex', gap: '5px' }}>
                    <input className="input-field" placeholder="retorna" value={newMethod.return_type} onChange={e => setNewMethod(m => ({ ...m, return_type: e.target.value }))} style={{ flex: 1, fontSize: '12px', padding: '5px 8px' }} />
                    <button className="btn btn-primary" onClick={handleAddMethod} style={{ padding: '5px 10px' }} title="Agregar método"><PlusCircle size={14} /></button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Modal de colaboradores */}
      <CollaboratorsModal
        isOpen={showCollabModal}
        onClose={() => setShowCollabModal(false)}
        project={currentProject}
      />

      {/* Modal de generación Spring Boot */}
      <GenerateBackendModal
        isOpen={showGenerateModal}
        onClose={() => setShowGenerateModal(false)}
        project={currentProject}
        nodes={nodes}
        edges={edges}
        onSaveBeforeGenerate={() => saveDiagram(nodesRef.current, edgesRef.current)}
      />

      {/* CU-08 — Modal de historial de versiones */}
      <HistoryModal
        isOpen={showHistoryModal}
        onClose={() => setShowHistoryModal(false)}
        projectId={id}
        onRestore={handleRestoreSnapshot}
      />

      {/* CU-09 — Panel de IA */}
      <AIChatPanel
        isOpen={showAIPanel}
        onClose={() => setShowAIPanel(false)}
        diagramData={{ nodes, edges }}
        onApplyAIUpdates={handleApplyAIUpdates}
      />
      {/* CU-10 — Modal imagen a UML */}
      <ImageToUMLModal
        isOpen={showImageModal}
        onClose={() => setShowImageModal(false)}
        onApply={handleApplyVisionDiagram}
      />

      {/* Chatbot Guía de Usuario — burbuja flotante esquina inferior derecha */}
      <HelpChatBot />
    </div>
  );
}

// Wrapper que provee el contexto de ReactFlow
export default function DiagramPage() {
  return (
    <ReactFlowProvider>
      <DiagramPageInner />
    </ReactFlowProvider>
  );
}
