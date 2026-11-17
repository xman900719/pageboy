import { describe, expect, it } from 'vitest'
import { evaluateStepClick, resolveActiveStepId, type StepDefinition } from './stepFlow'

const sampleSteps = (step2Unlocked: boolean): StepDefinition[] => [
  { id: 's1', title: '1. 选定对象', done: step2Unlocked, prereqMet: true },
  {
    id: 's2',
    title: '2. 详情核对',
    done: false,
    prereqMet: step2Unlocked,
    lockReason: '请先在第 1 步选定对象',
  },
  {
    id: 's3',
    title: '3. 人工审核',
    done: false,
    prereqMet: false,
    lockReason: '请先完成第 2 步核对',
  },
]

describe('stepFlow way-A helpers', () => {
  it('keeps requested step when unlocked and falls back to first unlocked step when locked', () => {
    expect(resolveActiveStepId(sampleSteps(false), 's2')).toBe('s1')
    expect(resolveActiveStepId(sampleSteps(true), 's2')).toBe('s2')
    expect(resolveActiveStepId(sampleSteps(true), 'missing')).toBe('s1')
  })

  it('falls back to step 0 when all steps are gated by an upstream tab prerequisite', () => {
    const allLocked: StepDefinition[] = [
      { id: 'u1', title: '1. 上传', done: false, prereqMet: false, lockReason: '请先建档' },
      { id: 'u2', title: '2. 解析', done: false, prereqMet: false, lockReason: '请先上传' },
    ]
    expect(resolveActiveStepId(allLocked, 'u2')).toBe('u1')
  })

  it('blocks skipping to locked steps with an explicit lock reason and allows unlocked steps', () => {
    const blocked = evaluateStepClick(sampleSteps(false), 's2')
    expect(blocked).toEqual({
      allowed: false,
      warning: '不可跳步至「2. 详情核对」：请先在第 1 步选定对象',
    })

    const allowed = evaluateStepClick(sampleSteps(true), 's2')
    expect(allowed).toEqual({
      allowed: true,
      nextId: 's2',
    })
  })
})
