export type EnsembleStateLabel = 'stable' | 'drift' | 'breakdown' | 'recovery'

export interface DashboardPayload {
  sessionId?: string
  songId?: string
  parts?: string[]
  breakdownPoint?: { bar?: number; beat?: number } | null
  recoveryPoint?: { bar?: number; beat?: number; reference_part?: string } | null
  partTimingDeviationMs?: Record<string, number>
  stateHistogram?: Record<string, number>
}

export interface LiveTickPayload {
  type: string
  sessionId: string
  ensembleState: {
    state: EnsembleStateLabel
    bar: number
    beat: number
    tempo: number
    leader: string | null
    deviatingParts: string[]
    breakdownRisk: number
  }
  sessionistAction: {
    role: string
    action: string
    target_tempo: number
    confidence: number
  }
  coaching: {
    message: string
    priority: number
  } | null
}
