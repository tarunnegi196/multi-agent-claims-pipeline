/**
 * PipelineGraph — 2×3 serpentine grid of agent cards.
 *
 * Layout (snake / serpentine flow — matches execution order):
 *   ┌──────────────┐  →  ┌──────────────┐
 *   │ 1. Intake    │     │ 2. Classify  │
 *   └──────────────┘     └──────────────┘
 *            ↙ (curves down-left)
 *   ┌──────────────┐  →  ┌──────────────┐
 *   │ 3. Verify    │     │ 4. Extract   │
 *   └──────────────┘     └──────────────┘
 *            ↙ (curves down-left)
 *   ┌──────────────┐  →  ┌──────────────┐
 *   │ 5. Fraud     │     │ 6. Decision  │
 *   └──────────────┘     └──────────────┘
 *
 * Clicking a card emits onNodeClick(agentName).
 * selectedAgent + status colouring are driven by parent state.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  ReactFlow, useNodesState, useEdgesState,
  Handle, Position, Background, BackgroundVariant,
} from '@xyflow/react'

/* ── Agent metadata ──────────────────────────────────────────────── */
export const AGENT_TO_NODE = {
  IntakeAgent:           'intake',
  DocClassifierAgent:    'classify',
  DocVerifierAgent:      'verify',
  ExtractionAgent:       'extract',
  FraudScreenAgent:      'fraud',
  DecisionComposerAgent: 'compose',
}

const NODE_DEFS = [
  /* col-left (x=0)  */
  { id: 'intake',   step: 1, label: 'Intake Agent',        sub: 'Member & amount validation',    agent: 'IntakeAgent',           x: 0,   y: 0,   tooltip: 'Validates member ID, claimed amount and policy eligibility' },
  { id: 'verify',   step: 3, label: 'Verifier Agent',      sub: 'Quality gate & completeness',   agent: 'DocVerifierAgent',      x: 0,   y: 200, tooltip: 'THE GATE — checks document quality & completeness. Halts on failure.' },
  { id: 'fraud',    step: 5, label: 'Fraud Screen Agent',  sub: 'Unusual-pattern checks',        agent: 'FraudScreenAgent',      x: 0,   y: 400, tooltip: 'Detects fraud signals: same-day claims, monthly limits, alterations' },
  /* col-right (x=300) */
  { id: 'classify', step: 2, label: 'Classifier Agent',    sub: 'Detects each document type',   agent: 'DocClassifierAgent',    x: 300, y: 0,   tooltip: 'Assigns document type to each file (PRESCRIPTION, HOSPITAL_BILL, etc.)' },
  { id: 'extract',  step: 4, label: 'Extraction Agent',    sub: 'Gemini Vision → structured data', agent: 'ExtractionAgent',    x: 300, y: 200, tooltip: 'Calls Gemini Vision to extract structured fields from documents' },
  { id: 'compose',  step: 6, label: 'Decision Agent',      sub: 'Policy engine gives verdict',   agent: 'DecisionComposerAgent', x: 300, y: 400, tooltip: 'Calls the deterministic policy engine & assembles final verdict' },
]

/* ── Status styles (Plum exact colours) ─────────────────────────── */
const S = {
  idle:   { border: '#460932', bg: 'rgba(70,9,50,0.3)',    text: '#9e708c', dot: '#7b5068', step: '#7b5068'  },
  active: { border: '#7b4067', bg: 'rgba(123,64,103,0.35)',text: '#d8c5d1', dot: '#7b4067', step: '#bea0b3'  },
  pass:   { border: '#92bd33', bg: 'rgba(146,189,51,0.12)',text: '#a9cb62', dot: '#92bd33', step: '#a9cb62'  },
  fail:   { border: '#ff4052', bg: 'rgba(255,64,82,0.15)', text: '#ffb7bb', dot: '#ff4052', step: '#ff4052'  },
  warn:   { border: '#ffbf21', bg: 'rgba(255,191,33,0.12)',text: '#ffbf21', dot: '#ffbf21', step: '#ffbf21'  },
  skip:   { border: '#340926', bg: 'rgba(52,9,38,0.2)',    text: '#570e40', dot: '#340926', step: '#460932'  },
}

/* ── Custom node ─────────────────────────────────────────────────── */
function AgentNode({ data, selected }) {
  const s       = S[data.status] || S.idle
  const isActive = data.status === 'active'
  const N        = data.step
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onClick={data.onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background:    s.bg,
        border:        `2px solid ${s.border}`,
        borderRadius:  14,
        padding:       '14px 16px',
        width:         220,
        minHeight:     128,
        cursor:        'pointer',
        outline:       selected ? `2px solid ${s.border}` : 'none',
        outlineOffset: 4,
        animation:     isActive ? 'node-glow 1.2s ease-in-out infinite' : 'none',
        transition:    'all 0.25s cubic-bezier(0.4, 0, 0.2, 1)',
        fontFamily:    'Inter, Arial, sans-serif',
        position:      'relative',
        pointerEvents: 'all',
        boxShadow:     selected
          ? `0 0 0 3px ${s.border}33, 0 8px 20px rgba(0,0,0,0.4)`
          : hovered
            ? `0 8px 20px rgba(0,0,0,0.35), inset 0 0 0 2px ${s.border}33`
            : 'none',
        transform:     hovered ? 'translateY(-4px) scale(1.02)' : 'translateY(0) scale(1)',
        userSelect:    'none',
      }}
    >
      <Handle type="target" position={Position.Left}
        style={{ background: s.border, border: 'none', width: 8, height: 8 }} />

      {/* Step badge */}
      <div style={{
        position: 'absolute', top: 10, right: 12,
        fontSize: 11, fontWeight: 800, color: s.step,
        background: `${s.border}22`, borderRadius: 99,
        padding: '2px 8px', letterSpacing: '0.04em',
        border: `1px solid ${s.border}44`,
      }}>
        {N} / 6
      </div>

      {/* Status dot */}
      <div style={{
        width: 9, height: 9, borderRadius: '50%',
        background: s.dot, marginBottom: 8,
        boxShadow: isActive ? `0 0 10px ${s.dot}` : 'none',
        transition: 'box-shadow 0.3s',
      }} />

      {/* Label */}
      <div style={{ fontWeight: 800, fontSize: 14, color: s.text, lineHeight: '18px', marginBottom: 4 }}>
        {data.label}
      </div>

      {/* Sub-description */}
      <div style={{ fontSize: 12, color: '#9e708c', lineHeight: '15px', marginBottom: 10 }}>
        {data.sub}
      </div>

      {/* Hover tooltip */}
      <div style={{
        fontSize: 11, color: '#d8c5d1', lineHeight: '14px',
        padding: '8px 10px', borderRadius: 8,
        background: hovered ? 'rgba(0,0,0,0.3)' : 'transparent',
        border: hovered ? `1px solid ${s.border}` : 'none',
        transition: 'all 0.25s ease',
        minHeight: hovered ? 'auto' : 0,
        opacity: hovered ? 1 : 0,
        overflow: 'hidden',
      }}>
        {hovered && (
          <>
            <span style={{ fontWeight: 600, color: s.text }}>Click to inspect</span>
            <span style={{ display: 'block', marginTop: 4, fontStyle: 'italic', fontSize: 10, color: '#9e708c' }}>
              {data.tooltip}
            </span>
          </>
        )}
      </div>

      <Handle type="source" position={Position.Right}
        style={{ background: s.border, border: 'none', width: 8, height: 8 }} />
    </div>
  )
}

const nodeTypes = { agent: AgentNode }

/* ── Edge builder ────────────────────────────────────────────────── */
function buildEdges(ns) {
  // Serpentine: intake→classify (→right), classify→verify (↙), verify→extract (→right), extract→fraud (↙), fraud→compose (→right)
  const pairs = [
    { id: 'e1', src: 'intake',   tgt: 'classify', agentKey: 'IntakeAgent'        },
    { id: 'e2', src: 'classify', tgt: 'verify',   agentKey: 'DocClassifierAgent' },
    { id: 'e3', src: 'verify',   tgt: 'extract',  agentKey: 'DocVerifierAgent'   },
    { id: 'e4', src: 'extract',  tgt: 'fraud',    agentKey: 'ExtractionAgent'    },
    { id: 'e5', src: 'fraud',    tgt: 'compose',  agentKey: 'FraudScreenAgent'   },
  ]

  return pairs.map(({ id, src, tgt, agentKey }) => {
    const status   = ns[agentKey]
    const animated = status === 'active'
    const color    = status === 'pass' ? '#92bd33' : status === 'fail' ? '#ff4052' : status === 'active' ? '#7b4067' : '#460932'
    return {
      id, source: src, target: tgt, type: 'smoothstep',
      animated,
      style: { stroke: color, strokeWidth: animated ? 2 : 1.5 },
    }
  })
}

/* ── Main component ──────────────────────────────────────────────── */
export default function PipelineGraph({ nodeStates = {}, nodeEvents = {}, selectedAgent, onNodeClick }) {
  const [nodes, setNodes, onNodesChange] = useNodesState([])
  const [edges, setEdges, onEdgesChange] = useEdgesState([])

  const handleClick = useCallback((agent) => { onNodeClick?.(agent) }, [onNodeClick])

  useEffect(() => {
    setNodes(NODE_DEFS.map((def) => ({
      id:   def.id,
      type: 'agent',
      position: { x: def.x, y: def.y },
      data: {
        label:   def.label,
        sub:     def.sub,
        step:    def.step,
        tooltip: def.tooltip,
        status:  nodeStates[def.agent] ?? 'idle',
        events:  nodeEvents[def.agent]  ?? [],
        onClick: () => handleClick(def.agent),
      },
      selected: selectedAgent === def.agent,
    })))
    setEdges(buildEdges(nodeStates))
  }, [nodeStates, nodeEvents, selectedAgent, handleClick])

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes} edges={edges}
        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        fitView fitViewOptions={{ padding: 0.12 }}
        nodesDraggable={false} nodesConnectable={false}
        elementsSelectable={false} panOnDrag={false}
        zoomOnScroll={false} zoomOnPinch={false} zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#2c0b21" />
      </ReactFlow>
    </div>
  )
}
