import type { DashboardPayload, LiveTickPayload } from './types'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export async function checkHealth(): Promise<boolean> {
  try {
    const r = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(1500) })
    return r.ok
  } catch {
    return false
  }
}

export async function createSyntheticAndAnalyze(): Promise<DashboardPayload | null> {
  // Dev helper: ask backend path-analyze if synthetic exists; otherwise null (UI uses storyboard)
  try {
    const body = {
      song_id: 'web_demo',
      midi_path: 'data/synthetic_demo/score.mid',
      parts: {
        vocal: 'data/synthetic_demo/vocal.wav',
        guitar: 'data/synthetic_demo/guitar.wav',
        bass: 'data/synthetic_demo/bass.wav',
        drums: 'data/synthetic_demo/drums.wav',
      },
      tempo_bpm: 120,
    }
    const r = await fetch(`${API_BASE}/api/v1/sessions/analyze/path`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(8000),
    })
    if (!r.ok) return null
    const report = await r.json()
    const sid = report.session_id as string
    const d = await fetch(`${API_BASE}/api/v1/sessions/${sid}/dashboard`)
    if (!d.ok) return null
    return (await d.json()) as DashboardPayload
  } catch {
    return null
  }
}

export async function postLiveTick(input: {
  sessionId: string
  timestamp: number
  bar: number
  beat: number
  tempo: number
  state: string
  spreadMs: number
  deviating: string[]
}): Promise<LiveTickPayload | null> {
  try {
    const r = await fetch(`${API_BASE}/api/v1/live/tick`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: input.sessionId,
        timestamp: input.timestamp,
        bar: input.bar,
        beat: input.beat,
        tempo: input.tempo,
        confidence: 0.9,
        user_part: 'guitar',
        sessionist_role: 'bass',
        sessionist_mode: 'follow',
        timing_spread_ms: input.spreadMs,
        state: input.state,
        deviating_parts: input.deviating,
        reference_part: 'drums',
      }),
      signal: AbortSignal.timeout(3000),
    })
    if (!r.ok) return null
    return (await r.json()) as LiveTickPayload
  } catch {
    return null
  }
}

export { API_BASE }
