# API Reference

Base URL: `http://127.0.0.1:8000`  
OpenAPI: `/docs` · `/redoc`  
Prefix: `/api/v1`

---

## Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | liveness |

---

## Phase 1 — Sessions / Offline Analysis

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/sessions` | Create session |
| GET | `/api/v1/sessions` | List sessions |
| GET | `/api/v1/sessions/{id}` | Get session |
| POST | `/api/v1/sessions/{id}/participants` | Add participant |
| POST | `/api/v1/sessions/{id}/analyze` | Upload MIDI + part WAVs, analyze |
| POST | `/api/v1/sessions/analyze/path` | Analyze from local paths (dev) |
| GET | `/api/v1/sessions/{id}/report` | Full analysis report |
| GET | `/api/v1/sessions/{id}/dashboard` | Compact dashboard JSON |
| GET | `/api/v1/sessions/{id}/state` | Last ensemble state sample |

### `POST /sessions/analyze/path` body

```json
{
  "song_id": "demo",
  "midi_path": "data/synthetic_demo/score.mid",
  "parts": {
    "vocal": "data/synthetic_demo/vocal.wav",
    "guitar": "data/synthetic_demo/guitar.wav",
    "bass": "data/synthetic_demo/bass.wav",
    "drums": "data/synthetic_demo/drums.wav"
  },
  "tempo_bpm": 120
}
```

---

## Phase 2 — Practice / Live Sessionist / Coaching

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/practice/analyze` | Personal practice + AI sessionist |
| GET | `/api/v1/practice/{id}/report` | Practice report |
| POST | `/api/v1/live/tick` | One realtime frame (action + coaching) |
| WS | `/api/v1/ws/sessions/{id}` | Subscribe to live events |

### Practice body highlights

```json
{
  "song_id": "demo",
  "midi_path": "data/synthetic_demo/score.mid",
  "user_part": "guitar",
  "user_wav_path": "data/synthetic_demo/guitar.wav",
  "sessionist_parts": ["bass", "drums"],
  "sessionist_mode": "follow",
  "tempo_bpm": 120,
  "render_audio": true
}
```

`render_paths` example keys: `mix_wav`, `mix_midi`, `bass_wav`, `drums_wav`

### Live tick body

```json
{
  "session_id": "live_demo",
  "timestamp": 3.0,
  "bar": 8,
  "beat": 1.0,
  "tempo": 118.0,
  "confidence": 0.92,
  "user_part": "guitar",
  "sessionist_role": "bass",
  "sessionist_mode": "follow",
  "timing_spread_ms": 180,
  "state": "breakdown",
  "deviating_parts": ["bass"],
  "reference_part": "drums"
}
```

---

## Phase 3 — Ensemble Room

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/rooms` | Create room |
| GET | `/api/v1/rooms` | List rooms |
| GET | `/api/v1/rooms/{id}` | Room detail |
| POST | `/api/v1/rooms/{id}/join` | Join with a part |
| POST | `/api/v1/rooms/{id}/score` | Upload MIDI (multipart) |
| POST | `/api/v1/rooms/{id}/score/path` | Set MIDI path (form) |
| POST | `/api/v1/rooms/{id}/parts/{user}/audio` | Upload member WAV |
| POST | `/api/v1/rooms/{id}/parts/{user}/audio/path` | Set WAV path (form) |
| POST | `/api/v1/rooms/{id}/start` | Mark rehearsing |
| POST | `/api/v1/rooms/{id}/analyze` | Analyze (+ optional AI fill) |
| GET | `/api/v1/rooms/{id}/dashboard` | Room dashboard |
| WS | `/api/v1/ws/rooms/{id}` | Room events |

### Join body

```json
{
  "user_id": "u1",
  "part_id": "guitar",
  "display_name": "Alex"
}
```

`part_id`: `vocal` | `guitar` | `bass` | `drums` | `keyboard`

### Analyze query

`POST /rooms/{id}/analyze?fill_missing_with_ai=true`

빈 파트(최대 2)를 Sessionist로 렌더해 채운 뒤 합주 분석합니다.

### Room WS events

- `subscribed`
- `member_joined`
- `score_uploaded` / `audio_uploaded`
- `rehearsal_started`
- `room_analyzed`

---

## Error style

FastAPI standard: `{ "detail": "..." }` with 4xx/5xx.
