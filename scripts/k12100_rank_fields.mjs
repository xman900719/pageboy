/**
 * k12100 本人排名白名单提取（在递归 PII 清洗前执行）。
 *
 * 只接受科目响应中的单值字段，不进入学生数组；同名字段不同值时丢弃该字段，
 * 绝不在浏览器侧猜测、补零或把冲突值合成为一条排名。
 */
const OWN_RANK_KEY_RE =
  /^(classrank|graderank|schoolrank|regionrank|examrank|classstudentnum|gradestudentnum|schoolstudentnum|regionstudentnum|examnum|actualexamnum|classrankrate|graderankrate|schoolrankrate|regionrankrate|examrankrate)$/i

export function extractOwnRankFields(value, depth = 0, out = {}) {
  if (depth > 4 || !value || typeof value !== 'object' || Array.isArray(value)) return out
  for (const [key, raw] of Object.entries(value)) {
    if (OWN_RANK_KEY_RE.test(String(key).trim()) && (typeof raw === 'string' || typeof raw === 'number')) {
      if (out[`${key}__conflict`]) continue
      const previous = out[key]
      if (previous === undefined || String(previous) === String(raw)) {
        out[key] = raw
      } else {
        out[`${key}__conflict`] = true
        delete out[key]
      }
    }
  }
  for (const nested of Object.values(value)) {
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      extractOwnRankFields(nested, depth + 1, out)
    }
  }
  return out
}

export function withoutRankConflicts(fields) {
  const clean = { ...fields }
  for (const key of Object.keys(clean)) {
    if (key.endsWith('__conflict')) {
      delete clean[key.slice(0, -'__conflict'.length)]
      delete clean[key]
    }
  }
  return clean
}


const EXAM_IDENTITY_KEY_RE =
  /^(schoolname|school_name|gradename|grade|examtypename|examtype|academicyear|academic_year|termname|term|seriestitle|series_title|examid)$/i

/**
 * 保留考试身份字段（学校/年级/类型/学年/学期/系列/平台 ID），供严格匹配使用。
 * 仍不读取学生数组、姓名/学号或凭据；同名字段冲突时丢弃，不猜测。
 */
export function extractExamIdentityFields(value, depth = 0, out = {}) {
  if (depth > 4 || !value || typeof value !== 'object' || Array.isArray(value)) return out
  for (const [key, raw] of Object.entries(value)) {
    if (EXAM_IDENTITY_KEY_RE.test(String(key).trim()) && (typeof raw === 'string' || typeof raw === 'number')) {
      if (out[`${key}__conflict`]) continue
      const previous = out[key]
      if (previous === undefined || String(previous) === String(raw)) {
        out[key] = raw
      } else {
        out[`${key}__conflict`] = true
        delete out[key]
      }
    }
  }
  for (const nested of Object.values(value)) {
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      extractExamIdentityFields(nested, depth + 1, out)
    }
  }
  return out
}

export function withoutIdentityConflicts(fields) {
  const clean = { ...fields }
  for (const key of Object.keys(clean)) {
    if (key.endsWith('__conflict')) {
      delete clean[key]
      delete clean[key.slice(0, -'__conflict'.length)]
    }
  }
  return clean
}

const STUDENT_REF_KEY_RE =
  /^(student_?id|stud_?id|student_?code|stud_?code|student_?no|stud_?no|stucode|stuno)$/i

/**
 * 只从当前科目响应中提取学生标识用于“归属一致性”比较。
 * 不读取数组（避免其他学生列表），不输出、不持久化原始标识。
 */
export function extractStudentIdentityRefs(value, depth = 0, out = new Set()) {
  if (depth > 4 || !value || typeof value !== 'object' || Array.isArray(value)) return out
  for (const [key, raw] of Object.entries(value)) {
    if (STUDENT_REF_KEY_RE.test(String(key).trim())) {
      const text = String(raw ?? '').trim()
      if (text) out.add(text)
    }
  }
  for (const nested of Object.values(value)) {
    if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
      extractStudentIdentityRefs(nested, depth + 1, out)
    }
  }
  return out
}
