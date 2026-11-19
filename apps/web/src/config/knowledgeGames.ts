import type {
  KnowledgeEdge,
  KnowledgeGameSubjectConfig,
  KnowledgeMasteryItem,
  KnowledgeGraph,
  MasteryStatus,
  Subject,
} from '../api'
import { getDomainLabel, getKnowledgeLabel } from './knowledge'

export type CardRarity = 'common' | 'rare' | 'epic' | 'ssr'

export interface AlchemyCard {
  id: string
  role: 'slot1' | 'slot2' | 'catalyst' | 'trap'
  tag: string
  icon: string
  name: string
  isCatalyst?: boolean
  isTrap?: boolean
  isRareOrigin?: boolean
}

export interface AlchemyRecipeStep {
  id: string
  stepIndex: number
  totalSteps: number
  targetCode: string
  targetName: string
  targetDesc: string
  targetStatus: MasteryStatus
  rarity: CardRarity
  rarityLabel: string
  slot1: {
    code: string
    name: string
    icon: string
    hint: string
    fromPrevStep: boolean
  }
  slot2: {
    code: string
    name: string
    icon: string
    hint: string
  }
  catalyst: {
    name: string
    hint: string
  }
  cards: AlchemyCard[]
}

export interface AlchemyChain {
  id: string
  title: string
  hasWeakTarget: boolean
  steps: AlchemyRecipeStep[]
}

export interface ExpeditionSlashOption {
  letter: 'A' | 'B' | 'C'
  text: string
  correct: boolean
}

export interface ExpeditionSlash {
  hitIndex: 1 | 2 | 3
  damage: number
  label: string
  question: string
  options: ExpeditionSlashOption[]
}

export interface ExpeditionZone {
  id: string
  title: string
  hasWeakBoss: boolean
  island1: {
    code: string
    name: string
    icon: string
    status: MasteryStatus
  }
  island2: {
    code: string
    name: string
    icon: string
    status: MasteryStatus
  }
  boss: {
    code: string
    name: string
    icon: string
    status: MasteryStatus
    observedRate: number | null
  }
  bridge1Label: string
  bridge2Label: string
  slashes: [ExpeditionSlash, ExpeditionSlash, ExpeditionSlash]
  secretTip: string
}

export interface SubjectGameProgress {
  resetEpoch: number
  exp: number
  bestCombo: number
  unlockedRecipeIds: string[]
  clearedZoneIds: string[]
  collectedTips: string[]
  soundEnabled: boolean
}

export const DEFAULT_GAME_CONFIG: Record<Subject, KnowledgeGameSubjectConfig> = {
  math: {
    subject: 'math',
    alchemy_enabled: true,
    expedition_enabled: true,
    initial_shields: 3,
    prioritize_weak: true,
    practice_gate: 'recommended',
    reset_epoch: 0,
  },
  chinese: {
    subject: 'chinese',
    alchemy_enabled: true,
    expedition_enabled: true,
    initial_shields: 3,
    prioritize_weak: true,
    practice_gate: 'recommended',
    reset_epoch: 0,
  },
  english: {
    subject: 'english',
    alchemy_enabled: true,
    expedition_enabled: true,
    initial_shields: 3,
    prioritize_weak: true,
    practice_gate: 'recommended',
    reset_epoch: 0,
  },
  physics: {
    subject: 'physics',
    alchemy_enabled: true,
    expedition_enabled: true,
    initial_shields: 3,
    prioritize_weak: true,
    practice_gate: 'recommended',
    reset_epoch: 0,
  },
}

const PROGRESS_KEY_PREFIX = 'shutong.knowledge_games.v1'

const SUBJECT_ICONS: Record<Subject, [string, string, string]> = {
  math: ['📐', '📈', '🧭'],
  physics: ['⚖️', '⚡', '🔋'],
  chinese: ['📜', '📖', '✍️'],
  english: ['🔤', '🧩', '⏱️'],
}

const RANK_TIERS: { minExp: number; title: string; icon: string }[] = [
  { minExp: 0, title: '启蒙学徒 Lv.1', icon: '🌱' },
  { minExp: 120, title: '破阵旅者 Lv.2', icon: '⚔️' },
  { minExp: 280, title: '概念炼金师 Lv.3', icon: '🔮' },
  { minExp: 500, title: '课标筑基师 Lv.4', icon: '🏅' },
  { minExp: 780, title: '中考宗师 Lv.5', icon: '👑' },
]

export function resolveRankSummary(exp: number): {
  title: string
  icon: string
  progressPct: number
  nextTease: string
} {
  let currentIdx = 0
  for (let i = 0; i < RANK_TIERS.length; i += 1) {
    if (exp >= RANK_TIERS[i].minExp) currentIdx = i
  }
  const cur = RANK_TIERS[currentIdx]
  const next = RANK_TIERS[currentIdx + 1]
  if (!next) {
    return {
      title: cur.title,
      icon: cur.icon,
      progressPct: 100,
      nextTease: '已登顶最高宗师段位',
    }
  }
  const span = Math.max(1, next.minExp - cur.minExp)
  const gained = Math.max(0, exp - cur.minExp)
  const progressPct = Math.min(96, Math.max(12, Math.round((gained / span) * 100)))
  const remain = next.minExp - exp
  const stepsLeft = Math.max(1, Math.ceil(remain / 100))
  return {
    title: cur.title,
    icon: cur.icon,
    progressPct,
    nextTease: `再闯 ${stepsLeft} 关即升 ${next.title}`,
  }
}

function displayNodeName(node: Pick<KnowledgeMasteryItem, 'code' | 'name'>): string {
  if (node.name && node.name !== node.code) return node.name
  return getKnowledgeLabel(node.code)
}

function resolveDomainChinese(
  node: KnowledgeMasteryItem,
  byCode: Map<string, KnowledgeMasteryItem>,
): string {
  if (node.domain) {
    const mapped = getDomainLabel(node.domain)
    if (mapped && mapped !== node.domain) return mapped
  }
  let cur: KnowledgeMasteryItem | undefined = node
  const seen = new Set<string>()
  while (cur?.parent_code && !seen.has(cur.code)) {
    seen.add(cur.code)
    const p = byCode.get(cur.parent_code)
    if (!p) break
    cur = p
  }
  return cur ? displayNodeName(cur) : '核心知识域'
}

function shortClause(text: string | null | undefined, fallback: string): string {
  const clean = (text ?? '').replace(/\s+/g, ' ').trim()
  if (!clean) return fallback
  return clean.length > 54 ? `${clean.slice(0, 54)}…` : clean
}

function statusPriority(status: MasteryStatus): number {
  if (status === 'weak') return 0
  if (status === 'untested') return 1
  if (status === 'insufficient') return 2
  return 3
}

function deterministicOrder<T>(items: T[], seedStr: string): T[] {
  const out = [...items]
  let hash = 0
  for (let i = 0; i < seedStr.length; i += 1) {
    hash = (hash * 31 + seedStr.charCodeAt(i)) >>> 0
  }
  for (let i = out.length - 1; i > 0; i -= 1) {
    hash = (hash * 1664525 + 1013904223) >>> 0
    const j = hash % (i + 1)
    const tmp = out[i]
    out[i] = out[j]
    out[j] = tmp
  }
  return out
}

function pickDistractorNode(
  excludeCodes: Set<string>,
  preferredDiffDomain: string | null | undefined,
  leaves: KnowledgeMasteryItem[],
  allNodes: KnowledgeMasteryItem[],
): KnowledgeMasteryItem | null {
  const crossDomain = leaves.find(
    n => !excludeCodes.has(n.code) && preferredDiffDomain && n.domain !== preferredDiffDomain,
  )
  if (crossDomain) return crossDomain
  const anyLeaf = leaves.find(n => !excludeCodes.has(n.code))
  if (anyLeaf) return anyLeaf
  return allNodes.find(n => !excludeCodes.has(n.code)) ?? null
}

/**
 * 基于图谱先修拓扑边与层级树构建「⚗️ 知识合成工坊」三阶滚雪球连续进化关卡。
 */
export function buildAlchemyCampaign(
  graph: KnowledgeGraph,
  config?: Partial<KnowledgeGameSubjectConfig>,
): AlchemyChain[] {
  const nodes = graph.nodes ?? []
  if (nodes.length < 3) return []

  const prioritizeWeak = config?.prioritize_weak ?? true
  const byCode = new Map(nodes.map(n => [n.code, n]))
  const leaves = nodes.filter(n => n.is_leaf)
  const pool = leaves.length >= 3 ? leaves : nodes

  const prereqEdges = (graph.edges ?? []).filter(
    (e: KnowledgeEdge) => e.edge_type === 'prerequisite' && byCode.has(e.source) && byCode.has(e.target),
  )

  const incoming = new Map<string, KnowledgeEdge[]>()
  const outgoing = new Map<string, KnowledgeEdge[]>()
  for (const e of prereqEdges) {
    const inList = incoming.get(e.target) ?? []
    inList.push(e)
    incoming.set(e.target, inList)

    const outList = outgoing.get(e.source) ?? []
    outList.push(e)
    outgoing.set(e.source, outList)
  }

  // 搜索长度为 3 或 2 的有向先修序列，构建滚雪球连续进化链
  interface RawChain {
    steps: { target: KnowledgeMasteryItem; p1: KnowledgeMasteryItem; rel: string }[]
  }
  const rawChains: RawChain[] = []
  const usedTargets = new Set<string>()

  for (const e1 of prereqEdges) {
    const a = byCode.get(e1.source)
    const b = byCode.get(e1.target)
    if (!a || !b || a.code === b.code) continue
    const nextEdges = outgoing.get(b.code) ?? []
    const e2 = nextEdges.find(x => x.target !== a.code && x.target !== b.code)
    if (e2) {
      const c = byCode.get(e2.target)
      if (c && !usedTargets.has(c.code)) {
        rawChains.push({
          steps: [
            { target: b, p1: a, rel: e1.relation || '前置支撑' },
            { target: c, p1: b, rel: e2.relation || '综合进阶' },
          ],
        })
        usedTargets.add(b.code)
        usedTargets.add(c.code)
      }
    }
  }

  // 补充尚未覆盖的单跳核心先修边（至少覆盖各领域）
  for (const e of prereqEdges) {
    const a = byCode.get(e.source)
    const b = byCode.get(e.target)
    if (!a || !b || a.code === b.code || usedTargets.has(b.code)) continue
    rawChains.push({
      steps: [{ target: b, p1: a, rel: e.relation || '核心推导' }],
    })
    usedTargets.add(b.code)
  }

  // 兜底：若测试图谱没有 prerequisite 边，基于同模块父子关系构建合成挑战
  if (rawChains.length === 0) {
    for (const leaf of pool.slice(0, 4)) {
      const sibling = pool.find(n => n.code !== leaf.code)
      if (!sibling) continue
      rawChains.push({
        steps: [{ target: leaf, p1: sibling, rel: `${resolveDomainChinese(leaf, byCode)}协同` }],
      })
    }
  }

  const icons = SUBJECT_ICONS[graph.subject] ?? ['📘', '🔬', '🎯']
  const chains: AlchemyChain[] = rawChains.map((rc, chainIdx) => {
    const total = rc.steps.length
    const hasWeakTarget = rc.steps.some(
      s => s.target.mastery_status === 'weak' || s.target.mastery_status === 'untested',
    )

    const builtSteps: AlchemyRecipeStep[] = rc.steps.map((st, sIdx) => {
      const target = st.target
      const p1 = st.p1
      const inEdges = incoming.get(target.code) ?? []
      const secondIncoming = inEdges.find(x => x.source !== p1.code)
      let p2: KnowledgeMasteryItem | undefined = secondIncoming
        ? byCode.get(secondIncoming.source)
        : undefined
      if (!p2) {
        p2 =
          pool.find(
            n => n.code !== target.code && n.code !== p1.code && n.parent_code === target.parent_code,
          ) ??
          (target.parent_code ? byCode.get(target.parent_code) : undefined) ??
          pool.find(n => n.code !== target.code && n.code !== p1.code) ??
          p1
      }

      const p1Name = displayNodeName(p1)
      const p2Name = displayNodeName(p2)
      const targetName = displayNodeName(target)
      const catalystName = st.rel.includes(targetName) ? st.rel : `${st.rel} ➔ 导出${targetName}`

      const exclude = new Set([target.code, p1.code, p2.code])
      const trapNode = pickDistractorNode(exclude, target.domain, pool, nodes)
      const trapName = trapNode ? displayNodeName(trapNode) : '无关跨章干扰概念'

      const fromPrevStep = sIdx > 0
      const rarity: CardRarity =
        sIdx === total - 1 ? (total >= 2 ? 'ssr' : 'epic') : 'rare'
      const rarityLabel =
        rarity === 'ssr' ? '🟠 传说 SSR' : rarity === 'epic' ? '🟣 史诗交汇' : '🔵 稀有枢纽'

      const cardsRaw: AlchemyCard[] = [
        {
          id: `${target.code}-slot1`,
          role: 'slot1',
          tag: fromPrevStep ? '🔵 上轮合成' : '🟢 前置基石',
          icon: icons[0],
          name: p1Name,
          isRareOrigin: fromPrevStep,
        },
        {
          id: `${target.code}-slot2`,
          role: 'slot2',
          tag: '🟢 前置基石',
          icon: icons[1],
          name: p2Name,
        },
        {
          id: `${target.code}-cat`,
          role: 'catalyst',
          tag: '⚡ 内在法则',
          icon: '⚡',
          name: catalystName,
          isCatalyst: true,
        },
        {
          id: `${target.code}-trap`,
          role: 'trap',
          tag: '💣 干扰陷阱',
          icon: '⭕',
          name: trapName,
          isTrap: true,
        },
      ]

      return {
        id: `alc:${target.code}`,
        stepIndex: sIdx,
        totalSteps: total,
        targetCode: target.code,
        targetName,
        targetDesc: shortClause(
          target.description,
          `${resolveDomainChinese(target, byCode)}核心考核要点`,
        ),
        targetStatus: target.mastery_status,
        rarity,
        rarityLabel,
        slot1: {
          code: p1.code,
          name: p1Name,
          icon: icons[0],
          hint: fromPrevStep ? '由上一轮进化自动载入' : '点击下方手牌投入',
          fromPrevStep,
        },
        slot2: {
          code: p2.code,
          name: p2Name,
          icon: icons[1],
          hint: '点击下方手牌投入',
        },
        catalyst: {
          name: catalystName,
          hint: '两块基石靠什么规律结合？',
        },
        cards: deterministicOrder(cardsRaw, `${graph.subject}:${target.code}`),
      }
    })

    const lastTarget = builtSteps[builtSteps.length - 1]
    return {
      id: `chain:${chainIdx}:${lastTarget.targetCode}`,
      title: `${resolveDomainChinese(rc.steps[0].target, byCode)} · ${lastTarget.targetName}`,
      hasWeakTarget,
      steps: builtSteps,
    }
  })

  if (prioritizeWeak) {
    chains.sort((a, b) => {
      if (a.hasWeakTarget !== b.hasWeakTarget) return a.hasWeakTarget ? -1 : 1
      return b.steps.length - a.steps.length
    })
  } else {
    chains.sort((a, b) => b.steps.length - a.steps.length)
  }

  return chains.slice(0, 12)
}

/**
 * 基于先修因果链构建「🧭 迷雾科技树探险」三岛破甲战区与三连斩挑战题组。
 */
export function buildExpeditionCampaign(
  graph: KnowledgeGraph,
  config?: Partial<KnowledgeGameSubjectConfig>,
): ExpeditionZone[] {
  const nodes = graph.nodes ?? []
  if (nodes.length < 3) return []

  const prioritizeWeak = config?.prioritize_weak ?? true
  const byCode = new Map(nodes.map(n => [n.code, n]))
  const leaves = nodes.filter(n => n.is_leaf)
  const pool = leaves.length >= 3 ? leaves : nodes

  const prereqEdges = (graph.edges ?? []).filter(
    (e: KnowledgeEdge) => e.edge_type === 'prerequisite' && byCode.has(e.source) && byCode.has(e.target),
  )

  interface TripleRoute {
    n1: KnowledgeMasteryItem
    n2: KnowledgeMasteryItem
    n3: KnowledgeMasteryItem
    rel1: string
    rel2: string
  }

  const routes: TripleRoute[] = []
  const seenBoss = new Set<string>()

  // 1. 优先采集标准 2-hop 先修航线 N1 -> N2 -> N3
  for (const e1 of prereqEdges) {
    const n1 = byCode.get(e1.source)
    const n2 = byCode.get(e1.target)
    if (!n1 || !n2 || n1.code === n2.code) continue
    for (const e2 of prereqEdges) {
      if (e2.source !== n2.code || e2.target === n1.code || e2.target === n2.code) continue
      const n3 = byCode.get(e2.target)
      if (!n3 || seenBoss.has(n3.code)) continue
      routes.push({
        n1,
        n2,
        n3,
        rel1: e1.relation || '前置支撑',
        rel2: e2.relation || '综合突破',
      })
      seenBoss.add(n3.code)
    }
  }

  // 2. 补充单跳先修边 N2 -> N3（借用同域前置/父模块作 N1）
  for (const e of prereqEdges) {
    const n2 = byCode.get(e.source)
    const n3 = byCode.get(e.target)
    if (!n2 || !n3 || n2.code === n3.code || seenBoss.has(n3.code)) continue
    const n1 =
      (n2.parent_code ? byCode.get(n2.parent_code) : undefined) ??
      pool.find(x => x.code !== n2.code && x.code !== n3.code && x.domain === n2.domain) ??
      pool.find(x => x.code !== n2.code && x.code !== n3.code)
    if (!n1) continue
    routes.push({
      n1,
      n2,
      n3,
      rel1: `${resolveDomainChinese(n2, byCode)}筑基`,
      rel2: e.relation || '核心推导',
    })
    seenBoss.add(n3.code)
  }

  // 3. 极简图谱兜底
  if (routes.length === 0 && pool.length >= 3) {
    routes.push({
      n1: pool[0],
      n2: pool[1],
      n3: pool[2],
      rel1: '基础衔接',
      rel2: '综合应用',
    })
  }

  const icons = SUBJECT_ICONS[graph.subject] ?? ['🧭', '📐', '🚩']
  const zones: ExpeditionZone[] = routes.map((rt, idx) => {
    const n1Name = displayNodeName(rt.n1)
    const n2Name = displayNodeName(rt.n2)
    const n3Name = displayNodeName(rt.n3)
    const n2Domain = resolveDomainChinese(rt.n2, byCode)

    const exclude = new Set([rt.n1.code, rt.n2.code, rt.n3.code])
    const distA = pickDistractorNode(exclude, rt.n2.domain, pool, nodes)
    if (distA) exclude.add(distA.code)
    const distB = pickDistractorNode(exclude, rt.n2.domain, pool, nodes)

    // 第 1 斩（-150 HP）：识破 2 号岛核心定义内涵
    const s1Choices = deterministicOrder(
      [
        {
          text: shortClause(rt.n2.description, `${n2Domain}中支撑「${n3Name}」的关键枢纽考点`),
          correct: true,
        },
        {
          text: shortClause(
            distA?.description,
            distA ? `${displayNodeName(distA)}的独立计算与概念辨析` : '跨学科无关概念的机械记忆',
          ),
          correct: false,
        },
        {
          text: shortClause(
            distB?.description,
            distB ? `${displayNodeName(distB)}的纯记忆性识记内容` : '仅适用于其他专题的独立方法',
          ),
          correct: false,
        },
      ],
      `${rt.n2.code}:s1`,
    )

    // 第 2 斩（-200 HP）：辨析所属课标知识域
    const allDomainNames = Array.from(
      new Set(nodes.map(n => resolveDomainChinese(n, byCode)).filter(Boolean)),
    )
    const otherDomains = allDomainNames.filter(d => d !== n2Domain)
    const d1 = otherDomains[0] || '综合与实践扩展域'
    const d2 = otherDomains[1] || '独立专题补充域'
    const s2Choices = deterministicOrder(
      [
        { text: `属于【${n2Domain}】，上承「${n1Name}」并支撑后续突破`, correct: true },
        { text: `属于【${d1}】，与「${n1Name}」没有任何先修关联`, correct: false },
        { text: `属于【${d2}】，属于不参与前置推导的选学拓展内容`, correct: false },
      ],
      `${rt.n2.code}:s2`,
    )

    // 第 3 斩（-650 HP 终结技）：打通先修桥梁关系
    const wrongRel1 =
      prereqEdges.find(e => e.target !== rt.n2.code && e.target !== rt.n3.code)?.relation ||
      '完全无关的独立模块对照'
    const s3Choices = deterministicOrder(
      [
        {
          text: `先修逻辑：由「${n1Name}」经「${rt.rel1}」铺垫，再通过「${rt.rel2}」直接攻克「${n3Name}」`,
          correct: true,
        },
        {
          text: `可跳过「${n1Name}」直接套用「${wrongRel1}」，无需前置概念支撑`,
          correct: false,
        },
        {
          text: `「${n3Name}」反而决定「${n1Name}」的基础定义，两者因果方向相反`,
          correct: false,
        },
      ],
      `${rt.n2.code}:s3`,
    )

    const letters: ('A' | 'B' | 'C')[] = ['A', 'B', 'C']
    const toOpts = (arr: { text: string; correct: boolean }[]): ExpeditionSlashOption[] =>
      arr.map((item, i) => ({ letter: letters[i], text: item.text, correct: item.correct }))

    const tipBody = shortClause(
      rt.n3.description || rt.n2.description,
      `解题先查「${n1Name} → ${n2Name}」先修基础是否稳固`,
    )

    return {
      id: `zone:${idx}:${rt.n3.code}`,
      title: `${n2Domain} · ${n3Name}`,
      hasWeakBoss: rt.n3.mastery_status === 'weak' || rt.n3.mastery_status === 'untested',
      island1: {
        code: rt.n1.code,
        name: n1Name,
        icon: icons[0],
        status: rt.n1.mastery_status,
      },
      island2: {
        code: rt.n2.code,
        name: n2Name,
        icon: icons[1],
        status: rt.n2.mastery_status,
      },
      boss: {
        code: rt.n3.code,
        name: n3Name,
        icon: '👹',
        status: rt.n3.mastery_status,
        observedRate: rt.n3.observed_rate,
      },
      bridge1Label: `${rt.rel1} ▶`,
      bridge2Label: `${rt.rel2} ▶`,
      slashes: [
        {
          hitIndex: 1,
          damage: 150,
          label: '第 1/3 斩：识破本质 (-150 HP)',
          question: `侦察【${n2Name}】据点：下列哪项准确描述了该考点的核心内涵？`,
          options: toOpts(s1Choices),
        },
        {
          hitIndex: 2,
          damage: 200,
          label: '第 2/3 斩：锁定战区 (-200 HP)',
          question: `定位【${n2Name}】在 2022 课标图谱中的归属与桥梁作用：`,
          options: toOpts(s2Choices),
        },
        {
          hitIndex: 3,
          damage: 650,
          label: '第 3/3 斩终结技：激光破甲 (-650 HP!)',
          question: `终极破甲：为什么【${n1Name}】与【${n2Name}】是攻克【${n3Name}】的必经先修航道？`,
          options: toOpts(s3Choices),
        },
      ],
      secretTip: `【${n2Name} ➔ ${n3Name} 避坑秘籍】${rt.rel2}核心要点：${tipBody}`,
    }
  })

  if (prioritizeWeak) {
    zones.sort((a, b) => statusPriority(a.boss.status) - statusPriority(b.boss.status))
  }

  return zones.slice(0, 10)
}

export function createEmptyProgress(resetEpoch = 0): SubjectGameProgress {
  return {
    resetEpoch,
    exp: 0,
    bestCombo: 0,
    unlockedRecipeIds: [],
    clearedZoneIds: [],
    collectedTips: [],
    soundEnabled: true,
  }
}

export function loadSubjectGameProgress(
  subject: Subject,
  serverResetEpoch = 0,
): SubjectGameProgress {
  const key = `${PROGRESS_KEY_PREFIX}.${subject}`
  try {
    if (typeof window === 'undefined' || !window.localStorage) {
      return createEmptyProgress(serverResetEpoch)
    }
    const raw = window.localStorage.getItem(key)
    if (!raw) return createEmptyProgress(serverResetEpoch)
    const parsed = JSON.parse(raw) as Partial<SubjectGameProgress>
    const storedEpoch = typeof parsed.resetEpoch === 'number' ? parsed.resetEpoch : 0
    // 若管理端已递增 reset_epoch，则自动清空本机旧游戏进度并同步新纪元
    if (serverResetEpoch > storedEpoch) {
      const fresh = createEmptyProgress(serverResetEpoch)
      fresh.soundEnabled = parsed.soundEnabled ?? true
      saveSubjectGameProgress(subject, fresh)
      return fresh
    }
    return {
      resetEpoch: storedEpoch,
      exp: typeof parsed.exp === 'number' ? parsed.exp : 0,
      bestCombo: typeof parsed.bestCombo === 'number' ? parsed.bestCombo : 0,
      unlockedRecipeIds: Array.isArray(parsed.unlockedRecipeIds) ? parsed.unlockedRecipeIds : [],
      clearedZoneIds: Array.isArray(parsed.clearedZoneIds) ? parsed.clearedZoneIds : [],
      collectedTips: Array.isArray(parsed.collectedTips) ? parsed.collectedTips : [],
      soundEnabled: typeof parsed.soundEnabled === 'boolean' ? parsed.soundEnabled : true,
    }
  } catch {
    return createEmptyProgress(serverResetEpoch)
  }
}

export function saveSubjectGameProgress(subject: Subject, progress: SubjectGameProgress): void {
  const key = `${PROGRESS_KEY_PREFIX}.${subject}`
  try {
    if (typeof window === 'undefined' || !window.localStorage) return
    window.localStorage.setItem(key, JSON.stringify(progress))
  } catch {
    // 忽略无痕模式或存储受限异常
  }
}
