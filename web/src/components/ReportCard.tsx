import type { DashboardPayload } from '../types'
import './ReportCard.css'

export function ReportCard({
  dashboard,
  fallback,
}: {
  dashboard: DashboardPayload | null
  fallback: { state: string; bar: number; tempo: number }
}) {
  const hist = dashboard?.stateHistogram
  const deviations = dashboard?.partTimingDeviationMs
  return (
    <div className="report">
      <h3>연습 리포트</h3>
      <p className="lead">어디서 흔들렸고, 어떻게 회복했는지 한눈에</p>
      <div className="report-grid">
        <div className="stat">
          <span className="k">현재 상태</span>
          <span className="v">{fallback.state}</span>
        </div>
        <div className="stat">
          <span className="k">마디 / 템포</span>
          <span className="v">
            {fallback.bar} · {fallback.tempo} BPM
          </span>
        </div>
        <div className="stat">
          <span className="k">무너진 지점</span>
          <span className="v">
            {dashboard?.breakdownPoint?.bar
              ? `${dashboard.breakdownPoint.bar}마디`
              : '데모: 17마디 근처'}
          </span>
        </div>
        <div className="stat">
          <span className="k">회복 지점</span>
          <span className="v">
            {dashboard?.recoveryPoint?.bar
              ? `${dashboard.recoveryPoint.bar}마디`
              : '데모: 20마디 근처'}
          </span>
        </div>
      </div>
      {hist && (
        <div className="bars">
          {Object.entries(hist).map(([k, n]) => {
            const max = Math.max(...Object.values(hist), 1)
            return (
              <div key={k} className="bar-row">
                <span>{k}</span>
                <div className="bar-track">
                  <div
                    className={`bar-fill ${k}`}
                    style={{ width: `${(n / max) * 100}%` }}
                  />
                </div>
              </div>
            )
          })}
        </div>
      )}
      {deviations && (
        <ul className="dev-list">
          {Object.entries(deviations).map(([part, ms]) => (
            <li key={part}>
              <strong>{part}</strong> 평균 편차 {ms.toFixed(0)} ms
            </li>
          ))}
        </ul>
      )}
      {!dashboard && (
        <p className="hint">
          백엔드가 켜져 있고 synthetic 데이터가 있으면 실제 분석 수치가 여기에 채워집니다.
        </p>
      )}
    </div>
  )
}
