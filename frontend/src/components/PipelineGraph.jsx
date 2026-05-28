import { useCallback, useEffect } from 'react'
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  Handle,
  Position,
  Background,
  Controls,
  BackgroundVariant,
} from '@xyflow/react'

const AGENT_TO_NODE = {
  IntakeAgent: 'intake',
  DocClassifierAgent: 'classify',
  DocVerifierAgent: 'verify',
  ExtractionAgent: 'extract',
  FraudScreenAgent: 'fraud',
  DecisionComposerAgent: 'compose',
}

const NODE_DEFS = [
  { id: 'intake',   label: 'Intake',         agent: 'IntakeAgent',           desc: 'Member · amount · docs',      x: 20  },
  { id: 'classify', label: 'Doc Classifier',  agent: 'DocClassifierAgent',    desc: 'Identifies doc types',        x: 210 },
  { id: 'verify',   label: 'Doc Verifier',    agent: 'DocVerifierAgent',      desc: 'Quality gate · completeness', x: 400 },
  { id: 'extract',  label: 'Extraction',      agent: 'ExtractionAgent',       desc: 'Gemini Vision → data',        x: 590 },
  { id: 'fraud',    label: 'Fraud Screen',    agent: 'FraudScreenAgent',      desc: 'Same-day · value flags',      x: 780 },
  { id: 'compose',  label: 'Decision',        agent: 'DecisionComposerAgent', desc: 'Policy engine · verdict',     x: 970 },
]

/* Plum-branded status palette */
const STATUS_STYLES = {
  idle:   { border: '#2A2550', bg: '#141130', text: '#6B6896', dot: '#3A3568' },
  active: { border: '#7C5CFC', bg: '#1D1555', text: '#C4B5FD', dot: '#7C5CFC' },
  pass:   { border: '#34d399', bg: '#022c22', text: '#A7F3D0', dot: '#34d399' },
  fail:   { border: '#F87171', bg: '#2D0A0A', text: '#FECACA', dot: '#F87171' },
  warn:   { border: '#FBBF24', bg: '#2D1A00', text: '#FDE68A', dot: '#FBBF24' },
  skip:   { border: '#2A2550', bg: '#0C0A1C', text: '#4B4878', dot: '#2A2550' },
}

function PipelineNode({ data, selected }) {
  const s = STATUS_STYLES[data.status] || STATUS_STYLES.idle
  const isActive = data.status === 'active'
  const eventCount = data.events?.length ?? 0

  return (
    <div
      onClick={data.onClick}
      style={{
        background: s.bg,
        border: `1.5px solid ${s.border}`,
        borderRadius: 10,
        padding: '10px 14px',
        minWidth: 148,
        cursor: 'pointer',
        outline: selected ? `2px solid ${s.border}` : 'none',
        outlineOffset: 3,
        animation: isActive ? 'node-glow 1.2s ease-in-out infinite' : 'none',
        transition: 'background 0.3s, border-color 0.3s, box-shadow 0.3s',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: s.border, border: 'none' }} />

      {/* Dot + label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%', background: s.dot, flexShrink: 0,
          boxShadow: isActive ? `0 0 7px ${s.dot}` : 'none',
        }} />
        <span style={{ fontWeight: 700, fontSize: 12, color: s.text, lineHeight: 1.2 }}>
          {data.label}
        </span>
      </div>

      {/* Description */}
      <div style={{ fontSize: 10, color: '#4B4878', marginBottom: eventCount > 0 ? 5 : 0 }}>
        {data.desc}
      </div>

      {/* Event badge */}
      {eventCount > 0 && (
        <div style={{
          fontSize: 10, color: s.dot, fontWeight: 700,
          background: `${s.dot}22`, borderRadius: 5,
          padding: '1px 7px', display: 'inline-block', border: `1px solid ${s.dot}44`,
        }}>
          {eventCount} event{eventCount !== 1 ? 's' : ''}
        </div>
      )}

      <Handle type="source" position={Position.Right} style={{ background: s.border, border: 'none' }} />
    </div>
  )
}

const nodeTypes = { pipeline: PipelineNode }

function buildNodes(nodeStates, nodeEvents, selectedAgent, onNodeClick) {
  return NODE_DEFS.map((def) => ({
    id: def.id,
    type: 'pipeline',
    position: { x: def.x, y: 60 },
    data: {
      label: def.label,
      desc: def.desc,
      status: nodeStates[def.agent] ?? 'idle',
      events: nodeEvents[def.agent] ?? [],
      onClick: () => onNodeClick(def.agent),
    },
    selected: selectedAgent === def.agent,
  }))
}

function buildEdges(nodeStates) {
  const pairs = [
    ['intake',  'classify', 'IntakeAgent'],
    ['classify','verify',   'DocClassifierAgent'],
    ['verify',  'extract',  'DocVerifierAgent'],
    ['extract', 'fraud',    'ExtractionAgent'],
    ['fraud',   'compose',  'FraudScreenAgent'],
  ]

  return pairs.map(([src, tgt, agentKey]) => {
    const status = nodeStates[agentKey]
    const animated = status === 'active'
    const color = status === 'pass' ? '#34d399' : status === 'fail' ? '#F87171' : '#2A2550'
    return {
      id: `e-${src}-${tgt}`,
      source: src,
      target: tgt,
      animated,
      style: { stroke: color, strokeWidth: animated ? 2 : 1.5 },
    }
  })
}

export default function PipelineGraph({ nodeStates = {}, nodeEvents = {}, selectedAgent, onNodeClick }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  const handleNodeClick = useCallback(
    (agent) => { onNodeClick?.(agent) },
    [onNodeClick],
  )

  useEffect(() => {
    setNodes(buildNodes(nodeStates, nodeEvents, selectedAgent, handleNodeClick))
    setEdges(buildEdges(nodeStates))
  }, [nodeStates, nodeEvents, selectedAgent, handleNodeClick])

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#1D1840" />
        <Controls showInteractive={false} style={{ bottom: 10, right: 10, top: 'auto', left: 'auto' }} />
      </ReactFlow>
    </div>
  )
}

export { AGENT_TO_NODE }
