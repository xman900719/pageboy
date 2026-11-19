import { describe, expect, it } from 'vitest'
import type { KnowledgeGraph, KnowledgeMasteryItem } from '../api'
import {
  LEAF_NODE_HEIGHT,
  LEAF_NODE_WIDTH,
  buildKnowledgeFlowGraph,
  collectLineage,
  resolveDisplayLeaves,
} from './knowledgeFlowLayout'

function makeNode(
  code: string,
  name: string,
  opts: Partial<KnowledgeMasteryItem> = {},
): KnowledgeMasteryItem {
  return {
    code,
    name,
    domain: opts.domain ?? 'num_alg',
    parent_code: opts.parent_code ?? null,
    level: opts.level ?? 2,
    description: null,
    is_leaf: opts.is_leaf ?? true,
    sample_size: opts.sample_size ?? 0,
    observed_rate: opts.observed_rate ?? null,
    mastery_status: opts.mastery_status ?? 'untested',
  }
}

const SAMPLE_GRAPH: KnowledgeGraph = {
  subject: 'math',
  release_version: 'math-v2022.1.0',
  model_version: 'v1.6-uncalibrated-rule',
  summary_counts: { mastered_count: 2, weak_count: 1, insufficient_count: 1, untested_count: 2 },
  nodes: [
    makeNode('math_cand.num_alg', '数与代数', { domain: 'num_alg', parent_code: null, level: 1, is_leaf: false }),
    makeNode('math_cand.num.rational', '有理数及其运算', {
      domain: 'num_alg',
      parent_code: 'math_cand.num_alg',
      mastery_status: 'mastered',
      observed_rate: 0.9,
      sample_size: 5,
    }),
    makeNode('math_cand.num.real', '实数与无理数概念及估算', {
      domain: 'num_alg',
      parent_code: 'math_cand.num_alg',
      mastery_status: 'weak',
      observed_rate: 0.4,
      sample_size: 5,
    }),
    makeNode('math_cand.alg.poly', '整式与乘法公式', {
      domain: 'num_alg',
      parent_code: 'math_cand.num_alg',
      mastery_status: 'insufficient',
      observed_rate: 0.5,
      sample_size: 2,
    }),
    makeNode('math_cand.alg.iso', '独立代数专题', {
      domain: 'num_alg',
      parent_code: 'math_cand.num_alg',
      mastery_status: 'untested',
    }),
    makeNode('math_cand.geo', '图形与几何', { domain: 'geom', parent_code: null, level: 1, is_leaf: false }),
    makeNode('math_cand.geo.coord', '平面直角坐标系', {
      domain: 'geom',
      parent_code: 'math_cand.geo',
      mastery_status: 'mastered',
      observed_rate: 0.85,
      sample_size: 4,
    }),
    makeNode('math_cand.geo.proj', '投影与三视图', {
      domain: 'geom',
      parent_code: 'math_cand.geo',
      mastery_status: 'untested',
    }),
  ],
  edges: [
    { source: 'math_cand.num_alg', target: 'math_cand.num.rational', relation: '所属模块', edge_type: 'hierarchy' },
    { source: 'math_cand.num.rational', target: 'math_cand.num.real', relation: '前置基础', edge_type: 'prerequisite' },
    { source: 'math_cand.num.real', target: 'math_cand.alg.poly', relation: '运算衔接', edge_type: 'prerequisite' },
    { source: 'math_cand.geo.coord', target: 'math_cand.alg.poly', relation: '数形结合', edge_type: 'prerequisite' },
  ],
}

describe('knowledgeFlowLayout 纯函数布局与脉络分析', () => {
  it('空图谱安全返回空布局', () => {
    const empty: KnowledgeGraph = {
      subject: 'math',
      model_version: 'v1',
      summary_counts: {},
      nodes: [],
      edges: [],
    }
    const built = buildKnowledgeFlowGraph(empty)
    expect(built.nodes).toHaveLength(0)
    expect(built.edges).toHaveLength(0)
    expect(built.leafCount).toBe(0)
  })

  it('过滤非叶子容器节点，仅渲染真实叶子考点且同容器内无坐标重叠', () => {
    const leaves = resolveDisplayLeaves(SAMPLE_GRAPH.nodes)
    expect(leaves.map(l => l.code)).not.toContain('math_cand.num_alg')
    expect(leaves.map(l => l.code)).not.toContain('math_cand.geo')
    expect(leaves).toHaveLength(6)

    const built = buildKnowledgeFlowGraph(SAMPLE_GRAPH, {
      selectedCode: 'math_cand.num.real',
    })

    const groupNodes = built.nodes.filter(n => n.type === 'domainGroup')
    const leafNodes = built.nodes.filter(n => n.type === 'knowledgeLeaf')
    expect(groupNodes).toHaveLength(2)
    expect(leafNodes).toHaveLength(6)

    // 检查同一父容器内任意两叶子节点包围盒不相交、坐标无 NaN
    const byParent = new Map<string, typeof leafNodes>()
    for (const n of leafNodes) {
      expect(Number.isFinite(n.position.x)).toBe(true)
      expect(Number.isFinite(n.position.y)).toBe(true)
      const list = byParent.get(n.parentId ?? '') ?? []
      list.push(n)
      byParent.set(n.parentId ?? '', list)
    }

    for (const groupLeaves of byParent.values()) {
      for (let i = 0; i < groupLeaves.length; i++) {
        for (let j = i + 1; j < groupLeaves.length; j++) {
          const a = groupLeaves[i].position
          const b = groupLeaves[j].position
          const overlapX = Math.abs(a.x - b.x) < LEAF_NODE_WIDTH
          const overlapY = Math.abs(a.y - b.y) < LEAF_NODE_HEIGHT
          expect(overlapX && overlapY).toBe(false)
        }
      }
    }

    // 跨领域桥梁识别正确
    expect(built.crossDomainBridges).toHaveLength(1)
    expect(built.crossDomainBridges[0].source).toBe('math_cand.geo.coord')
    expect(built.crossDomainBridges[0].target).toBe('math_cand.alg.poly')
  })

  it('collectLineage 精确追溯上下游前后置节点与边', () => {
    const lineage = collectLineage(SAMPLE_GRAPH.edges, 'math_cand.num.real')
    expect(Array.from(lineage.upstreamNodes)).toEqual(['math_cand.num.rational'])
    expect(Array.from(lineage.downstreamNodes)).toEqual(['math_cand.alg.poly'])
    expect(lineage.upstreamEdgeKeys.has('math_cand.num.rational=>math_cand.num.real')).toBe(true)
    expect(lineage.downstreamEdgeKeys.has('math_cand.num.real=>math_cand.alg.poly')).toBe(true)
    expect(lineage.upstreamEdgeKeys.has('math_cand.geo.coord=>math_cand.alg.poly')).toBe(false)
  })

  it('focusOnly 模式仅保留选中节点的关联脉络子图', () => {
    const built = buildKnowledgeFlowGraph(SAMPLE_GRAPH, {
      selectedCode: 'math_cand.num.real',
      focusOnly: true,
    })
    const leafIds = built.nodes.filter(n => n.type === 'knowledgeLeaf').map(n => n.id)
    expect(leafIds.sort()).toEqual([
      'math_cand.alg.poly',
      'math_cand.num.rational',
      'math_cand.num.real',
    ])
    expect(built.edges).toHaveLength(2)
    expect(built.edges.every(e => typeof e.label === 'string' && e.label.length > 0)).toBe(true)
  })

  it('onlyWeakHighlight 模式仅高亮未掌握节点并淡化其余节点', () => {
    const built = buildKnowledgeFlowGraph(SAMPLE_GRAPH, {
      onlyWeakHighlight: true,
      selectedCode: 'math_cand.num.rational',
    })
    const leafNodes = built.nodes.filter(n => n.type === 'knowledgeLeaf')
    const weakNode = leafNodes.find(n => n.id === 'math_cand.num.real')
    const masteredNode = leafNodes.find(n => n.id === 'math_cand.num.rational')
    expect(weakNode?.data.dimmed).toBe(false)
    expect(masteredNode?.data.dimmed).toBe(true)
  })
})
