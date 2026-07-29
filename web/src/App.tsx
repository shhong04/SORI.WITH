import { useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE, checkHealth, createSyntheticAndAnalyze, postLiveTick } from './api'
import { CoachBubble } from './components/CoachBubble'
import { ReportCard } from './components/ReportCard'
import { Stage } from './components/Stage'
import { STORY, frameAt } from './demo/scenario'
import type { DashboardPayload } from './types'
import './App.css'

type Tab = 'story' | 'room' | 'report'

const DURATION = STORY[STORY.length - 1].t

export default function App() {
  const [tab, setTab] = useState<Tab>('story')
  const [playing, setPlaying] = useState(true)
  const [time, setTime] = useState(0)
  const [aiOn, setAiOn] = useState(true)
  const [shake, setShake] = useState(0)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null)
  const [liveCoach, setLiveCoach] = useState<string | null>(null)
  const [pulse, setPulse] = useState(0)
  const lastTick = useRef(0)

  const frame = useMemo(() => frameAt(time, aiOn, shake), [time, aiOn, shake])

  useEffect(() => {
    let alive = true
    ;(async () => {
      const ok = await checkHealth()
      if (!alive) return
      setBackendOk(ok)
      if (ok) {
        const dash = await createSyntheticAndAnalyze()
        if (alive) setDashboard(dash)
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (!playing) return
    let raf = 0
    let last = performance.now()
    const loop = (now: number) => {
      const dt = (now - last) / 1000
      last = now
      setTime((t) => {
        const next = t + dt
        return next >= DURATION ? 0 : next
      })
      setPulse((p) => (p + dt * (frame.tempo / 60)) % 1)
      raf = requestAnimationFrame(loop)
    }
    raf = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(raf)
  }, [playing, frame.tempo])

  // Optional live tick sync when backend is up and state is unstable
  useEffect(() => {
    if (!backendOk || !aiOn) return
    if (frame.state === 'stable') {
      setLiveCoach(null)
      return
    }
    const now = performance.now()
    if (now - lastTick.current < 1800) return
    lastTick.current = now
    const spread =
      frame.state === 'breakdown' ? 180 : frame.state === 'drift' ? 100 : 50
    const deviating = Object.entries(frame.parts)
      .filter(([, p]) => p.active && Math.abs(p.offset) > 0.35)
      .map(([id]) => id)
    void postLiveTick({
      sessionId: 'web_demo_live',
      timestamp: time,
      bar: frame.bar,
      beat: frame.beat,
      tempo: frame.tempo,
      state: frame.state,
      spreadMs: spread,
      deviating,
    }).then((res) => {
      if (res?.coaching?.message) setLiveCoach(res.coaching.message)
    })
  }, [backendOk, aiOn, frame.state, frame.bar, frame.beat, frame.tempo, frame.parts, time])

  const coachMessage = liveCoach || frame.coach

  return (
    <div className="app">
      <header className="hero">
        <div>
          <p className="eyebrow">SORI.WITH Visual Demo</p>
          <h1>혼자여도 합주처럼, 함께일 땐 다시 맞게</h1>
          <p className="sub">
            비전문가도 이해하도록 — AI가 빈 파트를 채우고, 흔들림을 보여 주고, 짧게
            코칭합니다.
          </p>
        </div>
        <div className={`status-pill ${backendOk ? 'ok' : backendOk === false ? 'off' : ''}`}>
          {backendOk === null && '백엔드 확인 중…'}
          {backendOk === true && `API 연결됨 · ${API_BASE}`}
          {backendOk === false && '오프라인 스토리보드 모드'}
        </div>
      </header>

      <nav className="tabs">
        {(
          [
            ['story', '혼자 연습 + AI 세션'],
            ['room', '합주방 한눈에'],
            ['report', '리포트'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            className={tab === id ? 'active' : ''}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>

      {tab !== 'report' && (
        <section className="panel">
          <div className="copy">
            <div className={`badge ${frame.state}`}>{stateLabel(frame.state)}</div>
            <h2>{tab === 'room' ? '온라인 합주방' : frame.title}</h2>
            <p>{tab === 'room' ? '파트마다 앞뒤 위치가 어긋남을 보여줍니다.' : frame.subtitle}</p>
            <div className="meter">
              <span>
                {frame.bar}마디 · {frame.beat}박
              </span>
              <span>{frame.tempo} BPM</span>
            </div>
          </div>
          <Stage frame={frame} pulse={pulse} />
          <div className="side">
            <CoachBubble message={aiOn ? coachMessage : 'AI가 꺼져 있어요. 혼자 연주 중입니다.'} />
            <div className="controls">
              <button className="primary" onClick={() => setPlaying((p) => !p)}>
                {playing ? '일시정지' : '데모 재생'}
              </button>
              <button onClick={() => setTime(0)}>처음부터</button>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={aiOn}
                  onChange={(e) => setAiOn(e.target.checked)}
                />
                AI 멤버 ON
              </label>
              <label className="slider">
                <span>내가 빨라지기 / 늦어지기</span>
                <input
                  type="range"
                  min={-0.8}
                  max={0.8}
                  step={0.01}
                  value={shake}
                  onChange={(e) => setShake(Number(e.target.value))}
                />
              </label>
              <label className="slider">
                <span>타임라인</span>
                <input
                  type="range"
                  min={0}
                  max={DURATION}
                  step={0.1}
                  value={time}
                  onChange={(e) => {
                    setPlaying(false)
                    setTime(Number(e.target.value))
                  }}
                />
              </label>
              <p className="tip">
                AI를 끄면 반주가 사라지거나 따라오지 않습니다. 슬라이더로 템포를 흔들어
                보세요.
              </p>
            </div>
          </div>
        </section>
      )}

      {tab === 'report' && (
        <section className="panel report-panel">
          <ReportCard
            dashboard={dashboard}
            fallback={{ state: frame.state, bar: frame.bar, tempo: frame.tempo }}
          />
        </section>
      )}

      <footer className="foot">
        <span>SORI.WITH · Visual Demo</span>
        <a href="https://github.com/shhong04/SORI.WITH" target="_blank" rel="noreferrer">
          GitHub
        </a>
      </footer>
    </div>
  )
}

function stateLabel(s: string) {
  switch (s) {
    case 'stable':
      return '잘 맞음'
    case 'drift':
      return '흔들림'
    case 'breakdown':
      return '무너짐'
    case 'recovery':
      return '회복 중'
    default:
      return s
  }
}
