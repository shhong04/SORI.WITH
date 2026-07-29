import type { DemoFrame, PartId } from '../demo/scenario'
import { PART_META } from '../demo/scenario'
import './Stage.css'

export function Stage({
  frame,
  pulse,
}: {
  frame: DemoFrame
  pulse: number
}) {
  const ids = Object.keys(PART_META) as PartId[]
  return (
    <div className={`stage state-${frame.state}`}>
      <div className="stage-grid" />
      <div className="beat-ring" style={{ transform: `scale(${1 + pulse * 0.04})` }} />
      <div className="lanes">
        {ids.map((id) => {
          const meta = PART_META[id]
          const p = frame.parts[id]
          const x = p.offset * 70
          return (
            <div
              key={id}
              className={`lane ${p.active ? 'on' : 'off'}`}
              style={{ ['--c' as string]: meta.color }}
            >
              <div className="lane-label">
                <span className="emoji">{meta.emoji}</span>
                <span>{meta.label}</span>
                {p.active && id !== 'guitar' && (
                  <span className="tag">AI</span>
                )}
              </div>
              <div className="lane-track">
                <div className="center-line" />
                <div
                  className="avatar"
                  style={{
                    transform: `translateX(${x}px) scale(${p.active ? 1 : 0.85})`,
                    opacity: p.active ? 1 : 0.25,
                  }}
                  title={`${meta.label} offset ${p.offset.toFixed(2)}`}
                >
                  <span>{meta.emoji}</span>
                </div>
              </div>
              <div className="lane-hint">
                {!p.active
                  ? '대기'
                  : Math.abs(p.offset) < 0.12
                    ? '맞춤'
                    : p.offset < 0
                      ? '늦음'
                      : '빠름'}
              </div>
            </div>
          )
        })}
      </div>
      <div className="sync-legend">
        <span>← 늦음</span>
        <span className="mid">기준 박</span>
        <span>빠름 →</span>
      </div>
    </div>
  )
}
