import './CoachBubble.css'

export function CoachBubble({ message }: { message: string | null }) {
  if (!message) {
    return (
      <div className="coach empty">
        <div className="coach-label">AI 코치</div>
        <p>지금은 잘 맞고 있어요. 흐름을 유지해 보세요.</p>
      </div>
    )
  }
  return (
    <div className="coach active">
      <div className="coach-label">AI 코치</div>
      <p>{message}</p>
    </div>
  )
}
