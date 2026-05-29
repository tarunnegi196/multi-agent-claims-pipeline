/**
 * PipelineGraph — 2×4 serpentine grid of pipeline step cards.
 *
 * LLM nodes keep the "Agent" suffix + a GEMINI badge:
 *   Classifier Agent · Extraction Agent · Consistency Agent · Report Agent
 * Deterministic steps drop it: Intake · Verifier · Fraud Screen · Decision
 *
 * Each card shows a status pill (Idle / Running / Passed / Halted / Warning /
 * Skipped). Clicking a card emits onNodeClick(agentName).
 */
import { useCallback, useEffect, useState } from 'react'
import {
  ReactFlow, useNodesState, useEdgesState,
  Handle, Position, Background, BackgroundVariant, MarkerType,
} from '@xyflow/react'

/* ── Agent metadata ──────────────────────────────────────────────── */
export const AGENT_TO_NODE = {
  IntakeAgent:           'intake',
  DocClassifierAgent:    'classify',
  DocVerifierAgent:      'verify',
  ExtractionAgent:       'extract',
  ConsistencyAgent:      'consistency',
  FraudScreenAgent:      'fraud',
  DecisionComposerAgent: 'compose',
  ReportAgent:           'report',
}

// 2×4 grid. Big cards, generous gaps. Larger cards relative to gaps means
// fitView renders them bigger in the viewport.
const CARD_W    = 330
const GAP_X     = 130                 // horizontal gap between the two columns
const ROW_H     = 210                 // vertical stride between rows
const COL_LEFT  = 0
const COL_RIGHT = CARD_W + GAP_X

const NODE_DEFS = [
  { id: 'intake',      step: 1, label: 'Intake',            sub: 'Member & document validation',   agent: 'IntakeAgent',           isLLM: false, x: COL_LEFT,  y: 0 * ROW_H, tooltip: 'Validates member ID & document presence — deterministic, no LLM call.' },
  { id: 'classify',    step: 2, label: 'Classifier Agent',  sub: 'Gemini detects each doc type',   agent: 'DocClassifierAgent',    isLLM: true,  x: COL_RIGHT, y: 0 * ROW_H, tooltip: 'Gemini classifies each upload as PRESCRIPTION, HOSPITAL_BILL, etc. & rates readability.' },
  { id: 'verify',      step: 3, label: 'Verifier',          sub: 'Quality gate & completeness',    agent: 'DocVerifierAgent',      isLLM: false, x: COL_LEFT,  y: 1 * ROW_H, tooltip: 'THE GATE — every required doc type must be present & readable. Halts with a precise message if not.' },
  { id: 'extract',     step: 4, label: 'Extraction Agent',  sub: 'Fields + bounding boxes per doc',agent: 'ExtractionAgent',       isLLM: true,  x: COL_RIGHT, y: 1 * ROW_H, tooltip: 'Gemini Vision pulls every field + bounding box. Derives missing date/amount from bill totals.' },
  { id: 'consistency', step: 5, label: 'Consistency Agent', sub: 'Cross-document semantic check',  agent: 'ConsistencyAgent',      isLLM: true,  x: COL_LEFT,  y: 2 * ROW_H, tooltip: 'Gemini compares patient, doctor, hospital & dates across all docs — semantic match, not string equality.' },
  { id: 'fraud',       step: 6, label: 'Fraud Screen',      sub: 'Pattern & rule signals',         agent: 'FraudScreenAgent',      isLLM: false, x: COL_RIGHT, y: 2 * ROW_H, tooltip: 'Same-day · monthly · high-value · document alteration · cross-doc consistency flags.' },
  { id: 'compose',     step: 7, label: 'Decision',          sub: 'Deterministic policy engine',    agent: 'DecisionComposerAgent', isLLM: false, x: COL_LEFT,  y: 3 * ROW_H, tooltip: 'Policy engine: waiting periods, exclusions, network discount, copay, sub-limits → verdict + amount.' },
  { id: 'report',      step: 8, label: 'Report Agent',      sub: 'Narrative + next actions',       agent: 'ReportAgent',           isLLM: true,  x: COL_RIGHT, y: 3 * ROW_H, tooltip: 'Gemini synthesises a plain-English narrative, confidence reasoning and prioritised next-best-actions.' },
]

/* ── Status styles ───────────────────────────────────────────────── */
const S = {
  idle:   { border: '#460932', bg: 'rgba(70,9,50,0.28)',    text: '#9e708c', dot: '#7b5068', step: '#7b5068', label: 'Idle'    },
  active: { border: '#9b5080', bg: 'rgba(123,64,103,0.38)', text: '#e8d8e4', dot: '#d4a8c7', step: '#d4a8c7', label: 'Running' },
  pass:   { border: '#92bd33', bg: 'rgba(146,189,51,0.13)', text: '#b0ce5a', dot: '#92bd33', step: '#92bd33', label: 'Passed'  },
  fail:   { border: '#ff4052', bg: 'rgba(255,64,82,0.16)',  text: '#ffb7bb', dot: '#ff4052', step: '#ff4052', label: 'Halted'  },
  warn:   { border: '#ffbf21', bg: 'rgba(255,191,33,0.13)', text: '#ffe06a', dot: '#ffbf21', step: '#ffbf21', label: 'Warning' },
  skip:   { border: '#340926', bg: 'rgba(52,9,38,0.18)',    text: '#57304a', dot: '#340926', step: '#460932', label: 'Skipped' },
}

/* ── Custom node ─────────────────────────────────────────────────── */
function AgentNode({ data, selected }) {
  const s        = S[data.status] || S.idle
  const isActive = data.status === 'active'
  const [hovered, setHovered] = useState(false)

  return (
    <div
      onClick={data.onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background:    s.bg,
        border:        `2px solid ${s.border}`,
        borderRadius:  18,
        padding:       '18px 22px 18px',
        width:         CARD_W,
        cursor:        'pointer',
        outline:       selected ? `2.5px solid ${s.border}` : 'none',
        outlineOffset: 5,
        animation:     isActive ? 'node-glow 1.2s ease-in-out infinite' : 'none',
        transition:    'transform 0.22s cubic-bezier(0.4,0,0.2,1), box-shadow 0.22s cubic-bezier(0.4,0,0.2,1)',
        fontFamily:    'Inter, Arial, sans-serif',
        position:      'relative',
        pointerEvents: 'all',
        boxShadow: selected
          ? `0 0 0 4px ${s.border}44, 0 14px 34px rgba(0,0,0,0.55)`
          : hovered
            ? `0 12px 30px rgba(0,0,0,0.45), inset 0 0 0 1px ${s.border}55`
            : `0 2px 10px rgba(0,0,0,0.28)`,
        transform:     hovered ? 'translateY(-5px) scale(1.03)' : 'translateY(0) scale(1)',
        userSelect:    'none',
      }}
    >
      <Handle type="target" position={Position.Left}
        style={{ background: s.border, border: 'none', width: 11, height: 11, left: -6 }} />

      {/* Top bar: step badge left, status pill right */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <span style={{
          fontSize: 11, fontWeight: 900, color: s.step,
          background: `${s.border}28`, borderRadius: 99,
          padding: '4px 12px', letterSpacing: '0.06em',
          border: `1px solid ${s.border}55`, textTransform: 'uppercase',
        }}>
          Step {data.step}
        </span>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          fontSize: 11, fontWeight: 800, color: s.step,
          background: `${s.border}22`, border: `1px solid ${s.border}66`,
          borderRadius: 99, padding: '4px 12px',
          letterSpacing: '0.05em', textTransform: 'uppercase',
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
            background: s.dot,
            boxShadow: isActive ? `0 0 9px ${s.dot}` : 'none',
            animation: isActive ? 'pulse-dot 1.1s ease-in-out infinite' : 'none',
          }} />
          {s.label}
        </span>
      </div>

      {/* Label */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 7 }}>
        <span style={{ fontWeight: 800, fontSize: 18, color: s.text, lineHeight: '22px', letterSpacing: '-0.01em' }}>
          {data.label}
        </span>
        {data.isLLM && (
          <span style={{
            background: 'linear-gradient(135deg, #7b0050, #460932)',
            color: '#ffcce8', borderRadius: 5,
            padding: '2px 8px', fontSize: 9, fontWeight: 900,
            letterSpacing: '0.08em', flexShrink: 0,
            border: '1px solid rgba(190,160,179,0.25)',
          }}>
            GEMINI
          </span>
        )}
      </div>

      {/* Sub-description */}
      <div style={{ fontSize: 13.5, color: '#9e708c', lineHeight: '18px', marginBottom: 12 }}>
        {data.sub}
      </div>

      {/* Hover detail */}
      <div style={{
        overflow: 'hidden',
        maxHeight: hovered ? 90 : 0,
        opacity: hovered ? 1 : 0,
        transition: 'max-height 0.22s ease, opacity 0.18s ease',
      }}>
        <div style={{
          fontSize: 12, color: '#c4afc0', lineHeight: '17px',
          padding: '10px 12px', borderRadius: 10,
          background: 'rgba(0,0,0,0.32)',
          border: `1px solid ${s.border}66`,
        }}>
          <span style={{ fontWeight: 700, color: s.text, marginRight: 4 }}>↗ Click to inspect</span>
          {data.tooltip}
        </div>
      </div>

      <Handle type="source" position={Position.Right}
        style={{ background: s.border, border: 'none', width: 11, height: 11, right: -6 }} />
    </div>
  )
}

const nodeTypes = { agent: AgentNode }

/* ── Edge builder ────────────────────────────────────────────────── */
function buildEdges(ns) {
  const pairs = [
    { id: 'e1', src: 'intake',      tgt: 'classify',    agentKey: 'IntakeAgent'           },
    { id: 'e2', src: 'classify',    tgt: 'verify',      agentKey: 'DocClassifierAgent'    },
    { id: 'e3', src: 'verify',      tgt: 'extract',     agentKey: 'DocVerifierAgent'      },
    { id: 'e4', src: 'extract',     tgt: 'consistency', agentKey: 'ExtractionAgent'       },
    { id: 'e5', src: 'consistency', tgt: 'fraud',       agentKey: 'ConsistencyAgent'      },
    { id: 'e6', src: 'fraud',       tgt: 'compose',     agentKey: 'FraudScreenAgent'      },
    { id: 'e7', src: 'compose',     tgt: 'report',      agentKey: 'DecisionComposerAgent' },
  ]
  return pairs.map(({ id, src, tgt, agentKey }) => {
    const status   = ns[agentKey]
    const animated = status === 'active'
    const color = (
      status === 'pass'   ? '#92bd33' :
      status === 'fail'   ? '#ff4052' :
      status === 'warn'   ? '#ffbf21' :
      status === 'active' ? '#9b5080' :
      '#460932'
    )
    return {
      id, source: src, target: tgt, type: 'smoothstep',
      animated,
      style: { stroke: color, strokeWidth: animated ? 2.5 : 1.5 },
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
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
        isLLM:   def.isLLM,
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
        fitView fitViewOptions={{ padding: 0.08 }}
        nodesDraggable={false} nodesConnectable={false}
        elementsSelectable={false} panOnDrag={false}
        zoomOnScroll={false} zoomOnPinch={false} zoomOnDoubleClick={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={28} size={1.2} color="#2c0b21" />
      </ReactFlow>
    </div>
  )
}
