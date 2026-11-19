import { describe, it, expect, beforeEach } from 'vitest'
import type { KnowledgeGraph } from '../api'
import {
  buildAlchemyCampaign,
  buildExpeditionCampaign,
  loadSubjectGameProgress,
  resolveRankSummary,
  saveSubjectGameProgress,
} from './knowledgeGames'

function makeSampleMathGraph(): KnowledgeGraph {
  return {
    subject: 'math',
    release_version: 'math-v2022.1.0',
    model_version: 'v2',
    summary_counts: { mastered_count: 2, weak_count: 2, insufficient_count: 0, untested_count: 2 },
    nodes: [
      {
        code: 'math_cand.num_alg',
        name: '数与代数',
        domain: 'num_alg',
        parent_code: null,
        level: 1,
        description: '数与式、方程与不等式、函数领域。',
        is_leaf: false,
        sample_size: 4,
        observed_rate: 0.75,
        mastery_status: 'mastered',
      },
      {
        code: 'math_cand.alg.poly',
        name: '整式与乘法公式',
        domain: 'num_alg',
        parent_code: 'math_cand.num_alg',
        level: 3,
        description: '整式加减乘除与平方差、完全平方公式。',
        is_leaf: true,
        sample_size: 4,
        observed_rate: 0.85,
        mastery_status: 'mastered',
      },
      {
        code: 'math_cand.alg.factor',
        name: '因式分解',
        domain: 'num_alg',
        parent_code: 'math_cand.num_alg',
        level: 3,
        description: '提公因式法与公式法将多项式化为整式乘积。',
        is_leaf: true,
        sample_size: 3,
        observed_rate: 0.75,
        mastery_status: 'mastered',
      },
      {
        code: 'math_cand.alg.frac',
        name: '分式及其运算',
        domain: 'num_alg',
        parent_code: 'math_cand.num_alg',
        level: 3,
        description: '分式约分通分与加减乘除混合运算。',
        is_leaf: true,
        sample_size: 3,
        observed_rate: 0.45,
        mastery_status: 'weak',
      },
      {
        code: 'math_cand.eq.fractional',
        name: '分式方程',
        domain: 'num_alg',
        parent_code: 'math_cand.num_alg',
        level: 3,
        description: '化为整式方程求解并检验增根。',
        is_leaf: true,
        sample_size: 3,
        observed_rate: 0.4,
        mastery_status: 'weak',
      },
      {
        code: 'math_cand.geom',
        name: '图形与几何',
        domain: 'geom',
        parent_code: null,
        level: 1,
        description: '三角形、四边形与圆的性质及证明。',
        is_leaf: false,
        sample_size: 0,
        observed_rate: null,
        mastery_status: 'untested',
      },
      {
        code: 'math_cand.geo.circle_basic',
        name: '圆的基本性质',
        domain: 'geom',
        parent_code: 'math_cand.geom',
        level: 3,
        description: '垂径定理、圆心角与圆周角定理。',
        is_leaf: true,
        sample_size: 0,
        observed_rate: null,
        mastery_status: 'untested',
      },
    ],
    edges: [
      { source: 'math_cand.num_alg', target: 'math_cand.alg.poly', relation: '所属模块', edge_type: 'hierarchy' },
      { source: 'math_cand.alg.poly', target: 'math_cand.alg.factor', relation: '互逆变形', edge_type: 'prerequisite' },
      { source: 'math_cand.alg.factor', target: 'math_cand.alg.frac', relation: '约分通分支撑', edge_type: 'prerequisite' },
      { source: 'math_cand.alg.frac', target: 'math_cand.eq.fractional', relation: '分式化简与验根', edge_type: 'prerequisite' },
    ],
  }
}

describe('knowledgeGames 双游戏确定性生成引擎与进度隔离', () => {
  beforeEach(() => {
    const store = new Map<string, string>()
    Object.defineProperty(globalThis, 'window', {
      value: {
        localStorage: {
          getItem: (k: string) => store.get(k) ?? null,
          setItem: (k: string, v: string) => store.set(k, v),
          removeItem: (k: string) => store.delete(k),
        },
      },
      configurable: true,
    })
  })

  it('构建知识合成工坊滚雪球进化链：含 4 张手牌（基石/法则/干扰）且无内部英文编码裸露', () => {
    const graph = makeSampleMathGraph()
    const chains = buildAlchemyCampaign(graph, { prioritize_weak: true })
    expect(chains.length).toBeGreaterThan(0)
    expect(chains[0].hasWeakTarget).toBe(true)

    const multiStep = chains.find(c => c.steps.length >= 2)
    expect(multiStep).toBeDefined()
    const step0 = multiStep!.steps[0]
    const step1 = multiStep!.steps[1]
    expect(step0.slot1.fromPrevStep).toBe(false)
    expect(step1.slot1.fromPrevStep).toBe(true)
    expect(step1.rarity).toBe('ssr')

    for (const st of multiStep!.steps) {
      expect(st.cards).toHaveLength(4)
      expect(st.cards.filter(c => c.role === 'trap')).toHaveLength(1)
      expect(st.cards.filter(c => c.role === 'catalyst')).toHaveLength(1)
      const joined = [st.targetName, st.slot1.name, st.slot2.name, st.catalyst.name, ...st.cards.map(c => c.name)].join(' ')
      expect(joined).not.toContain('math_cand.')
      expect(joined).not.toContain('num_alg')
    }
  })

  it('构建迷雾科技树探险三岛航线：含 1000 HP 破甲三连斩且优先排序薄弱 BOSS 要塞', () => {
    const graph = makeSampleMathGraph()
    const zones = buildExpeditionCampaign(graph, { prioritize_weak: true })
    expect(zones.length).toBeGreaterThan(0)
    expect(zones[0].hasWeakBoss).toBe(true)

    for (const z of zones) {
      expect(z.slashes).toHaveLength(3)
      const totalDamage = z.slashes.reduce((acc, s) => acc + s.damage, 0)
      expect(totalDamage).toBe(1000)
      for (const s of z.slashes) {
        expect(s.options).toHaveLength(3)
        expect(s.options.filter(o => o.correct)).toHaveLength(1)
      }
      expect(z.island1.name).not.toContain('math_cand.')
      expect(z.island2.name).not.toContain('math_cand.')
      expect(z.boss.name).not.toContain('math_cand.')
    }
  })

  it('反例：空图谱或不足 3 节点时安全返回空数组而不抛异常', () => {
    const emptyGraph: KnowledgeGraph = {
      subject: 'physics',
      model_version: 'v2',
      summary_counts: {},
      nodes: [],
      edges: [],
    }
    expect(buildAlchemyCampaign(emptyGraph)).toEqual([])
    expect(buildExpeditionCampaign(emptyGraph)).toEqual([])
  })

  it('段位经验晋升与管理端 reset_epoch 递增自动重置本机游戏进度', () => {
    const r0 = resolveRankSummary(0)
    expect(r0.title).toContain('Lv.1')
    expect(r0.nextTease).toContain('再闯')

    const rMax = resolveRankSummary(900)
    expect(rMax.title).toContain('Lv.5')
    expect(rMax.progressPct).toBe(100)

    saveSubjectGameProgress('math', {
      resetEpoch: 0,
      exp: 320,
      bestCombo: 6,
      unlockedRecipeIds: ['alc:math_cand.alg.frac'],
      clearedZoneIds: ['zone:0:math_cand.eq.fractional'],
      collectedTips: ['秘籍1'],
      soundEnabled: false,
    })

    const kept = loadSubjectGameProgress('math', 0)
    expect(kept.exp).toBe(320)
    expect(kept.unlockedRecipeIds).toHaveLength(1)

    // 管理端点击「重置本学科游戏进度」使 reset_epoch 从 0 变为 1
    const reset = loadSubjectGameProgress('math', 1)
    expect(reset.resetEpoch).toBe(1)
    expect(reset.exp).toBe(0)
    expect(reset.unlockedRecipeIds).toEqual([])
    expect(reset.clearedZoneIds).toEqual([])
    // 保留用户的静音偏好
    expect(reset.soundEnabled).toBe(false)
  })
})
