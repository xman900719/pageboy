import dagre from '@dagrejs/dagre'
import { MarkerType, type Edge, type Node } from '@xyflow/vue'
import type {
  KnowledgeEdge,
  KnowledgeGraph,
  KnowledgeMasteryItem,
  MasteryStatus,
} from '../api'
import { getDomainLabel, getKnowledgeLabel } from './knowledge'

export const LEAF_NODE_WIDTH = 186
export const LEAF_NODE_HEIGHT = 70

export interface KnowledgeFlowOptions {
  domainFilter?: string
  selectedCode?: string | null
  onlyWeakHighlight?: boolean
  focusOnly?: boolean
}

export interface DomainGroupNodeData extends Record<string, unknown> {
  label: string
  domainKey: string
  totalLeaves: number
  masteredCount: number
  weakCount: number
  hideStats?: boolean
}

export type LineageRole = 'selected' | 'upstream' | 'downstream' | 'none'

export interface KnowledgeLeafNodeData extends Record<string, unknown> {
  item: KnowledgeMasteryItem
  displayName: string
  status: MasteryStatus
  observedRate: number | null
  hasWeakUpstream: boolean
  lineageRole: LineageRole
  dimmed: boolean
}

export interface KnowledgeFlowEdgeData extends Record<string, unknown> {
  relation: string
  isCrossDomain: boolean
  lineageRole: 'upstream' | 'downstream' | 'none'
  dimmed: boolean
}

export interface CrossDomainBridgeItem {
  key: string
  source: string
  sourceName: string
  target: string
  targetName: string
  relation: string
  weakWarning: boolean
  active: boolean
}

export interface LineageResult {
  upstreamNodes: Set<string>
  downstreamNodes: Set<string>
  upstreamEdgeKeys: Set<string>
  downstreamEdgeKeys: Set<string>
}

export interface BuiltKnowledgeFlow {
  nodes: Node[]
  edges: Edge<KnowledgeFlowEdgeData>[]
  lineage: LineageResult
  crossDomainBridges: CrossDomainBridgeItem[]
  leafCount: number
}

export function nodeDisplayName(node: Pick<KnowledgeMasteryItem, 'code' | 'name'>): string {
  if (node.name && node.name !== node.code) return node.name
  return getKnowledgeLabel(node.code)
}

function edgeKey(source: string, target: string): string {
  return `${source}=>${target}`
}

/**
 * 筛选出真实叶子考点节点（排除仅用于层级聚合的一级领域与二级模块标题节点）。
 */
export function resolveDisplayLeaves(nodes: KnowledgeMasteryItem[]): KnowledgeMasteryItem[] {
  if (nodes.length === 0) return []
  const parentsWithChildren = new Set<string>()
  for (const n of nodes) {
    if (n.parent_code) {
      parentsWithChildren.add(n.parent_code)
    }
  }
  const leaves = nodes.filter(n => n.is_leaf || !parentsWithChildren.has(n.code))
  return leaves.length > 0 ? leaves : nodes
}

export function resolveDomainKeyAndLabel(
  node: KnowledgeMasteryItem,
  byCode: Map<string, KnowledgeMasteryItem>,
): { key: string; label: string } {
  if (node.domain) {
    const mapped = getDomainLabel(node.domain)
    if (mapped && mapped !== node.domain) {
      return { key: node.domain, label: mapped }
    }
  }
  let cur: KnowledgeMasteryItem | undefined = node
  const seen = new Set<string>()
  while (cur?.parent_code && !seen.has(cur.code)) {
    seen.add(cur.code)
    const parent = byCode.get(cur.parent_code)
    if (!parent) break
    cur = parent
  }
  if (cur) {
    const key = cur.domain || cur.code
    const mapped = cur.domain ? getDomainLabel(cur.domain) : ''
    const label = mapped && mapped !== cur.domain ? mapped : nodeDisplayName(cur)
    return { key, label }
  }
  const fallbackKey = node.domain || node.code
  return { key: fallbackKey, label: getDomainLabel(fallbackKey) }
}

/**
 * 沿先修边做双向 BFS，收集选中节点的完整前置链路（upstream）与后续进阶链路（downstream）。
 */
export function collectLineage(
  edges: KnowledgeEdge[],
  selectedCode: string | null | undefined,
): LineageResult {
  const upstreamNodes = new Set<string>()
  const downstreamNodes = new Set<string>()
  const upstreamEdgeKeys = new Set<string>()
  const downstreamEdgeKeys = new Set<string>()

  if (!selectedCode) {
    return { upstreamNodes, downstreamNodes, upstreamEdgeKeys, downstreamEdgeKeys }
  }

  const prereqEdges = edges.filter(e => e.edge_type === 'prerequisite')

  const upQueue: string[] = [selectedCode]
  while (upQueue.length > 0) {
    const cur = upQueue.shift()!
    for (const e of prereqEdges) {
      if (e.target === cur && e.source !== selectedCode) {
        upstreamEdgeKeys.add(edgeKey(e.source, e.target))
        if (!upstreamNodes.has(e.source)) {
          upstreamNodes.add(e.source)
          upQueue.push(e.source)
        }
      }
    }
  }

  const downQueue: string[] = [selectedCode]
  while (downQueue.length > 0) {
    const cur = downQueue.shift()!
    for (const e of prereqEdges) {
      if (e.source === cur && e.target !== selectedCode) {
        downstreamEdgeKeys.add(edgeKey(e.source, e.target))
        if (!downstreamNodes.has(e.target)) {
          downstreamNodes.add(e.target)
          downQueue.push(e.target)
        }
      }
    }
  }

  return { upstreamNodes, downstreamNodes, upstreamEdgeKeys, downstreamEdgeKeys }
}

interface SubgraphLayout {
  positions: Map<string, { x: number; y: number }>
  width: number
  height: number
}

function layoutSubgraphTB(
  subNodes: KnowledgeMasteryItem[],
  subEdges: KnowledgeEdge[],
  nodeW: number,
  nodeH: number,
  nodesep: number,
  ranksep: number,
): SubgraphLayout {
  const positions = new Map<string, { x: number; y: number }>()
  if (subNodes.length === 0) {
    return { positions, width: nodeW, height: nodeH }
  }

  const nodeSet = new Set(subNodes.map(n => n.code))
  const validEdges = subEdges.filter(
    e => e.edge_type === 'prerequisite' && nodeSet.has(e.source) && nodeSet.has(e.target) && e.source !== e.target,
  )
  const connected = new Set<string>()
  for (const e of validEdges) {
    connected.add(e.source)
    connected.add(e.target)
  }

  let dagWidth = 0
  let dagHeight = 0

  if (connected.size > 0) {
    const g = new dagre.graphlib.Graph({ multigraph: false })
    g.setGraph({
      rankdir: 'TB',
      nodesep,
      ranksep,
      edgesep: 18,
      marginx: 0,
      marginy: 0,
    })
    g.setDefaultEdgeLabel(() => ({}))

    for (const n of subNodes) {
      if (connected.has(n.code)) {
        g.setNode(n.code, { width: nodeW, height: nodeH })
      }
    }
    for (const e of validEdges) {
      g.setEdge(e.source, e.target)
    }

    dagre.layout(g)

    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity

    const rawPos = new Map<string, { x: number; y: number }>()
    for (const id of g.nodes()) {
      const box = g.node(id)
      if (!box || Number.isNaN(box.x) || Number.isNaN(box.y)) continue
      const x = box.x - nodeW / 2
      const y = box.y - nodeH / 2
      rawPos.set(id, { x, y })
      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x + nodeW)
      maxY = Math.max(maxY, y + nodeH)
    }

    if (Number.isFinite(minX) && Number.isFinite(minY)) {
      for (const [id, p] of rawPos.entries()) {
        positions.set(id, {
          x: Math.round(p.x - minX),
          y: Math.round(p.y - minY),
        })
      }
      dagWidth = Math.round(maxX - minX)
      dagHeight = Math.round(maxY - minY)
    }
  }

  const isolated = subNodes.filter(n => !positions.has(n.code))
  if (isolated.length > 0) {
    const startY = dagHeight > 0 ? dagHeight + 28 : 0
    const cols = Math.max(2, Math.min(3, Math.ceil(Math.sqrt(isolated.length))))
    const isoGapX = Math.max(16, Math.round(nodesep * 0.85))
    const isoGapY = 16
    isolated.forEach((n, idx) => {
      const col = idx % cols
      const row = Math.floor(idx / cols)
      const x = col * (nodeW + isoGapX)
      const y = startY + row * (nodeH + isoGapY)
      positions.set(n.code, { x, y })
      dagWidth = Math.max(dagWidth, x + nodeW)
      dagHeight = Math.max(dagHeight, y + nodeH)
    })
  }

  return {
    positions,
    width: Math.max(dagWidth, nodeW),
    height: Math.max(dagHeight, nodeH),
  }
}

export function buildKnowledgeFlowGraph(
  graph: KnowledgeGraph,
  options: KnowledgeFlowOptions = {},
): BuiltKnowledgeFlow {
  const domainFilter = options.domainFilter ?? 'all'
  const selectedCode = options.selectedCode ?? null
  const onlyWeakHighlight = options.onlyWeakHighlight ?? false
  const focusOnly = options.focusOnly ?? false

  const allNodes = graph.nodes ?? []
  const allEdges = graph.edges ?? []
  const byCode = new Map(allNodes.map(n => [n.code, n]))
  const allLeaves = resolveDisplayLeaves(allNodes)
  const lineage = collectLineage(allEdges, selectedCode)

  const weakUpstreamByCode = new Set<string>()
  for (const e of allEdges) {
    if (e.edge_type !== 'prerequisite') continue
    const src = byCode.get(e.source)
    if (src?.mastery_status === 'weak') {
      weakUpstreamByCode.add(e.target)
    }
  }

  const domainOf = (n: KnowledgeMasteryItem) => resolveDomainKeyAndLabel(n, byCode)

  // 跨领域桥梁速览（供画布底部快捷跳转使用）
  const crossDomainBridges: CrossDomainBridgeItem[] = []
  const prereqEdges = allEdges.filter(e => e.edge_type === 'prerequisite')
  prereqEdges.forEach((e, idx) => {
    const src = byCode.get(e.source)
    const tgt = byCode.get(e.target)
    if (!src || !tgt) return
    const sDom = domainOf(src)
    const tDom = domainOf(tgt)
    if (sDom.key === tDom.key) return
    if (domainFilter !== 'all' && sDom.key !== domainFilter && tDom.key !== domainFilter) return
    crossDomainBridges.push({
      key: `${e.source}->${e.target}-${idx}`,
      source: src.code,
      sourceName: nodeDisplayName(src),
      target: tgt.code,
      targetName: nodeDisplayName(tgt),
      relation: e.relation || '跨领域支撑',
      weakWarning: src.mastery_status === 'weak',
      active: selectedCode === src.code || selectedCode === tgt.code,
    })
  })

  // 筛选参与画布渲染的叶子节点
  let targetLeaves: KnowledgeMasteryItem[]
  if (focusOnly && selectedCode && byCode.has(selectedCode)) {
    const keepCodes = new Set<string>([
      selectedCode,
      ...lineage.upstreamNodes,
      ...lineage.downstreamNodes,
    ])
    targetLeaves = allLeaves.filter(n => keepCodes.has(n.code))
    if (targetLeaves.length === 0 && byCode.get(selectedCode)) {
      targetLeaves = [byCode.get(selectedCode)!]
    }
  } else if (domainFilter !== 'all') {
    targetLeaves = allLeaves.filter(n => {
      const dom = domainOf(n)
      return dom.key === domainFilter || n.domain === domainFilter || n.code === domainFilter
    })
  } else {
    targetLeaves = allLeaves
  }

  if (targetLeaves.length === 0) {
    return { nodes: [], edges: [], lineage, crossDomainBridges, leafCount: 0 }
  }

  const hasSelected = Boolean(selectedCode && targetLeaves.some(n => n.code === selectedCode))
  const nodes: Node[] = []

  const makeLeafNode = (
    leaf: KnowledgeMasteryItem,
    parentId: string,
    x: number,
    y: number,
  ): Node<KnowledgeLeafNodeData> => {
    let lineageRole: LineageRole = 'none'
    if (selectedCode === leaf.code) lineageRole = 'selected'
    else if (lineage.upstreamNodes.has(leaf.code)) lineageRole = 'upstream'
    else if (lineage.downstreamNodes.has(leaf.code)) lineageRole = 'downstream'

    let dimmed = false
    if (onlyWeakHighlight) {
      dimmed = leaf.mastery_status !== 'weak'
    } else if (!focusOnly && hasSelected && lineageRole === 'none') {
      dimmed = true
    }

    return {
      id: leaf.code,
      type: 'knowledgeLeaf',
      parentId,
      extent: 'parent',
      zIndex: 3,
      position: { x, y },
      draggable: false,
      selectable: false,
      connectable: false,
      focusable: false,
      data: {
        item: leaf,
        displayName: nodeDisplayName(leaf),
        status: leaf.mastery_status,
        observedRate: leaf.observed_rate,
        hasWeakUpstream: weakUpstreamByCode.has(leaf.code),
        lineageRole,
        dimmed,
      },
    }
  }

  if (focusOnly && selectedCode) {
    const groupId = 'group::lineage'
    const lay = layoutSubgraphTB(targetLeaves, prereqEdges, LEAF_NODE_WIDTH, LEAF_NODE_HEIGHT, 28, 50)
    const padX = 22
    const padTop = 46
    const padBot = 20
    const groupW = Math.max(lay.width + padX * 2, 340)
    const groupH = lay.height + padTop + padBot
    const innerOffsetX = Math.round((groupW - lay.width) / 2)

    nodes.push({
      id: groupId,
      type: 'domainGroup',
      zIndex: 0,
      position: { x: 16, y: 16 },
      draggable: false,
      selectable: false,
      connectable: false,
      focusable: false,
      style: { width: `${groupW}px`, height: `${groupH}px` },
      data: {
        label: `选中节点因果脉络子图（共 ${targetLeaves.length} 个关联考点）`,
        domainKey: 'lineage',
        totalLeaves: targetLeaves.length,
        masteredCount: targetLeaves.filter(l => l.mastery_status === 'mastered').length,
        weakCount: targetLeaves.filter(l => l.mastery_status === 'weak').length,
        hideStats: true,
      } satisfies DomainGroupNodeData,
    })

    for (const leaf of targetLeaves) {
      const p = lay.positions.get(leaf.code) ?? { x: 0, y: 0 }
      nodes.push(makeLeafNode(leaf, groupId, innerOffsetX + p.x, padTop + p.y))
    }
  } else {
    // 按领域分组 + 两列均衡瀑布流装箱
    const grouped = new Map<string, { label: string; leaves: KnowledgeMasteryItem[] }>()
    for (const leaf of targetLeaves) {
      const dom = domainOf(leaf)
      let bucket = grouped.get(dom.key)
      if (!bucket) {
        bucket = { label: dom.label, leaves: [] }
        grouped.set(dom.key, bucket)
      }
      bucket.leaves.push(leaf)
    }

    const padX = 18
    const padTop = 46
    const padBot = 18
    const colGap = 24
    const rowGap = 24

    const entries = Array.from(grouped.entries()).map(([domKey, info]) => {
      const domLeafSet = new Set(info.leaves.map(l => l.code))
      const intraEdges = prereqEdges.filter(e => domLeafSet.has(e.source) && domLeafSet.has(e.target))
      const lay = layoutSubgraphTB(
        info.leaves,
        intraEdges,
        LEAF_NODE_WIDTH,
        LEAF_NODE_HEIGHT,
        22,
        46,
      )
      return {
        domKey,
        label: info.label,
        leaves: info.leaves,
        lay,
        width: Math.max(lay.width + padX * 2, 260),
        height: lay.height + padTop + padBot,
      }
    })

    if (entries.length === 1) {
      const only = entries[0]
      const groupId = `group::${only.domKey}`
      nodes.push({
        id: groupId,
        type: 'domainGroup',
        zIndex: 0,
        position: { x: 16, y: 16 },
        draggable: false,
        selectable: false,
        connectable: false,
        focusable: false,
        style: { width: `${only.width}px`, height: `${only.height}px` },
        data: {
          label: only.label,
          domainKey: only.domKey,
          totalLeaves: only.leaves.length,
          masteredCount: only.leaves.filter(l => l.mastery_status === 'mastered').length,
          weakCount: only.leaves.filter(l => l.mastery_status === 'weak').length,
        } satisfies DomainGroupNodeData,
      })
      for (const leaf of only.leaves) {
        const p = only.lay.positions.get(leaf.code) ?? { x: 0, y: 0 }
        nodes.push(makeLeafNode(leaf, groupId, padX + p.x, padTop + p.y))
      }
    } else {
      // 两列均衡装箱：将每个领域放入当前高度较小的一列，同时保持两列宽度各自对齐
      const colAssignments: { col: 0 | 1; entry: (typeof entries)[number] }[] = []
      let h0 = 16
      let h1 = 16
      for (const entry of entries) {
        const col: 0 | 1 = h0 <= h1 ? 0 : 1
        colAssignments.push({ col, entry })
        if (col === 0) h0 += entry.height + rowGap
        else h1 += entry.height + rowGap
      }

      const col0MaxW = Math.max(
        260,
        ...colAssignments.filter(a => a.col === 0).map(a => a.entry.width),
      )
      const col1MaxW = Math.max(
        260,
        ...colAssignments.filter(a => a.col === 1).map(a => a.entry.width),
      )

      let y0 = 16
      let y1 = 16
      for (const { col, entry } of colAssignments) {
        const x = col === 0 ? 16 : 16 + col0MaxW + colGap
        const y = col === 0 ? y0 : y1
        const boxW = col === 0 ? col0MaxW : col1MaxW
        const offsetX = Math.round((boxW - entry.lay.width) / 2)
        const groupId = `group::${entry.domKey}`

        nodes.push({
          id: groupId,
          type: 'domainGroup',
          zIndex: 0,
          position: { x, y },
          draggable: false,
          selectable: false,
          connectable: false,
          focusable: false,
          style: { width: `${boxW}px`, height: `${entry.height}px` },
          data: {
            label: entry.label,
            domainKey: entry.domKey,
            totalLeaves: entry.leaves.length,
            masteredCount: entry.leaves.filter(l => l.mastery_status === 'mastered').length,
            weakCount: entry.leaves.filter(l => l.mastery_status === 'weak').length,
          } satisfies DomainGroupNodeData,
        })

        for (const leaf of entry.leaves) {
          const p = entry.lay.positions.get(leaf.code) ?? { x: 0, y: 0 }
          nodes.push(makeLeafNode(leaf, groupId, offsetX + p.x, padTop + p.y))
        }

        if (col === 0) y0 += entry.height + rowGap
        else y1 += entry.height + rowGap
      }
    }
  }

  // 构建边
  const renderedLeafCodes = new Set(targetLeaves.map(l => l.code))
  const edges: Edge<KnowledgeFlowEdgeData>[] = []

  prereqEdges.forEach((e, idx) => {
    if (!renderedLeafCodes.has(e.source) || !renderedLeafCodes.has(e.target)) return
    const src = byCode.get(e.source)
    const tgt = byCode.get(e.target)
    if (!src || !tgt) return

    const isCrossDomain = domainOf(src).key !== domainOf(tgt).key
    const key = edgeKey(e.source, e.target)
    const isUp = lineage.upstreamEdgeKeys.has(key)
    const isDown = lineage.downstreamEdgeKeys.has(key)
    const lineageRole: 'upstream' | 'downstream' | 'none' = isUp
      ? 'upstream'
      : isDown
        ? 'downstream'
        : 'none'
    const isActive = lineageRole !== 'none'
    const dimmed = !focusOnly && hasSelected && !isActive

    const stroke =
      lineageRole === 'upstream'
        ? '#d97724'
        : lineageRole === 'downstream'
          ? '#265d75'
          : isCrossDomain
            ? '#4d87a1'
            : '#8d8275'

    edges.push({
      id: `edge-${e.source}-${e.target}-${idx}`,
      source: e.source,
      target: e.target,
      type: isCrossDomain ? 'default' : 'smoothstep',
      animated: false,
      focusable: false,
      selectable: false,
      label: isActive || focusOnly ? e.relation || '前置支撑' : undefined,
      labelShowBg: false,
      labelStyle: isActive || focusOnly
        ? {
            fill: '#000000',
            fontWeight: 700,
            fontSize: '11px',
          }
        : undefined,
      labelBgStyle: {
        fill: 'transparent',
        fillOpacity: 0,
        stroke: 'none',
      },
      style: {
        stroke,
        strokeWidth: isActive ? 2.5 : 1.5,
        strokeDasharray: isCrossDomain ? '6 4' : undefined,
        opacity: dimmed ? 0.2 : 1,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 16,
        height: 16,
        color: stroke,
      },
      data: {
        relation: e.relation || '前置支撑',
        isCrossDomain,
        lineageRole,
        dimmed,
      },
    })
  })

  return {
    nodes,
    edges,
    lineage,
    crossDomainBridges,
    leafCount: targetLeaves.length,
  }
}
