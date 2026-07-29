import type { EnsembleStateLabel } from '../types'

export type PartId = 'vocal' | 'guitar' | 'bass' | 'drums'

export interface PartVisual {
  id: PartId
  label: string
  emoji: string
  color: string
  /** -1 late … 0 synced … +1 early */
  offset: number
  isAi: boolean
  active: boolean
}

export interface DemoFrame {
  t: number
  title: string
  subtitle: string
  state: EnsembleStateLabel
  coach: string | null
  parts: Record<PartId, { offset: number; active: boolean }>
  bar: number
  beat: number
  tempo: number
}

/** 60s storyboard for non-experts (offline fallback + narration beats) */
export const STORY: DemoFrame[] = [
  {
    t: 0,
    title: '혼자 연습 중',
    subtitle: '기타만 연주하고 있어요',
    state: 'stable',
    coach: null,
    bar: 1,
    beat: 1,
    tempo: 120,
    parts: {
      vocal: { offset: 0, active: false },
      guitar: { offset: 0, active: true },
      bass: { offset: 0, active: false },
      drums: { offset: 0, active: false },
    },
  },
  {
    t: 8,
    title: 'AI 멤버가 합류',
    subtitle: '빈 자리(베이스·드럼)를 AI가 채웁니다',
    state: 'stable',
    coach: 'AI 세션이 당신 템포에 맞춰 들어옵니다.',
    bar: 5,
    beat: 1,
    tempo: 120,
    parts: {
      vocal: { offset: 0, active: false },
      guitar: { offset: 0, active: true },
      bass: { offset: 0, active: true },
      drums: { offset: 0, active: true },
    },
  },
  {
    t: 18,
    title: '템포가 조금 빨라졌어요',
    subtitle: '고정 반주라면 어긋나지만, AI는 따라갑니다',
    state: 'stable',
    coach: null,
    bar: 9,
    beat: 1,
    tempo: 126,
    parts: {
      vocal: { offset: 0, active: false },
      guitar: { offset: 0.15, active: true },
      bass: { offset: 0.12, active: true },
      drums: { offset: 0.1, active: true },
    },
  },
  {
    t: 28,
    title: '합주가 흔들립니다',
    subtitle: '베이스가 드럼보다 늦어지고 있어요',
    state: 'drift',
    coach: '베이스와 드럼 간격이 커지고 있습니다. 다음 마디 첫 박에서 드럼을 기준으로 맞춰주세요.',
    bar: 13,
    beat: 3,
    tempo: 118,
    parts: {
      vocal: { offset: 0, active: true },
      guitar: { offset: 0.05, active: true },
      bass: { offset: -0.7, active: true },
      drums: { offset: 0.05, active: true },
    },
  },
  {
    t: 40,
    title: '거의 무너질 뻔…',
    subtitle: 'AI가 핵심만 짧게 코칭합니다',
    state: 'breakdown',
    coach: '합주 위치가 갈라지고 있습니다. 다음 마디 첫 박에서 드럼을 기준으로 맞춰주세요.',
    bar: 17,
    beat: 2,
    tempo: 112,
    parts: {
      vocal: { offset: 0.2, active: true },
      guitar: { offset: -0.3, active: true },
      bass: { offset: -0.85, active: true },
      drums: { offset: 0.1, active: true },
    },
  },
  {
    t: 50,
    title: '다시 맞춰집니다',
    subtitle: '회복 구간 — 팀이 같은 강박으로 모입니다',
    state: 'recovery',
    coach: '회복 중입니다. 드럼의 강박을 기준으로 유지해주세요.',
    bar: 20,
    beat: 1,
    tempo: 120,
    parts: {
      vocal: { offset: 0.05, active: true },
      guitar: { offset: 0.02, active: true },
      bass: { offset: -0.15, active: true },
      drums: { offset: 0, active: true },
    },
  },
  {
    t: 58,
    title: '연습 리포트',
    subtitle: '어디서 흔들렸고, 어떻게 회복했는지 요약',
    state: 'stable',
    coach: null,
    bar: 24,
    beat: 1,
    tempo: 120,
    parts: {
      vocal: { offset: 0, active: true },
      guitar: { offset: 0, active: true },
      bass: { offset: 0, active: true },
      drums: { offset: 0, active: true },
    },
  },
]

export const PART_META: Record<
  PartId,
  { label: string; emoji: string; color: string }
> = {
  vocal: { label: '보컬', emoji: '🎤', color: '#e85d4c' },
  guitar: { label: '기타', emoji: '🎸', color: '#2a9d8f' },
  bass: { label: '베이스', emoji: '🎻', color: '#3d5a80' },
  drums: { label: '드럼', emoji: '🥁', color: '#e9c46a' },
}

export function frameAt(timeSec: number, aiEnabled: boolean, shake: number): DemoFrame {
  const clamped = Math.max(0, Math.min(timeSec, STORY[STORY.length - 1].t))
  let i = 0
  while (i < STORY.length - 1 && STORY[i + 1].t <= clamped) i += 1
  const a = STORY[i]
  const b = STORY[Math.min(i + 1, STORY.length - 1)]
  const span = Math.max(0.001, b.t - a.t)
  const w = i === STORY.length - 1 ? 0 : (clamped - a.t) / span

  const lerp = (x: number, y: number) => x + (y - x) * w
  const parts = {} as DemoFrame['parts']
  ;(Object.keys(a.parts) as PartId[]).forEach((id) => {
    const pa = a.parts[id]
    const pb = b.parts[id]
    let offset = lerp(pa.offset, pb.offset)
    // user shake pushes guitar early/late; AI follows if enabled
    if (id === 'guitar') offset += shake
    if (aiEnabled && (id === 'bass' || id === 'drums')) {
      offset += shake * 0.85
    } else if (!aiEnabled && (id === 'bass' || id === 'drums')) {
      // fixed backing stays put → looks more off when user shakes
      offset = lerp(pa.offset, pb.offset) * (pa.active || pb.active ? 1 : 0)
    }
    const active =
      id === 'guitar'
        ? true
        : aiEnabled
          ? w < 0.5
            ? pa.active
            : pb.active
          : id === 'vocal'
            ? w < 0.5
              ? pa.active
              : pb.active
            : false
    parts[id] = {
      offset: Math.max(-1, Math.min(1, offset)),
      active,
    }
  })

  // refine active for non-ai: only guitar
  if (!aiEnabled) {
    parts.bass.active = false
    parts.drums.active = false
    parts.vocal.active = false
  }

  return {
    t: clamped,
    title: w < 0.5 ? a.title : b.title,
    subtitle: w < 0.5 ? a.subtitle : b.subtitle,
    state: w < 0.55 ? a.state : b.state,
    coach: w < 0.5 ? a.coach : b.coach,
    parts,
    bar: Math.round(lerp(a.bar, b.bar)),
    beat: Math.round(lerp(a.beat, b.beat)),
    tempo: Math.round(lerp(a.tempo, b.tempo) + shake * 8),
  }
}
