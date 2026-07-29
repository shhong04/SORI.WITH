# SORI.WITH

**AI Ensemble Platform** — SORI의 Audio-to-MIDI · Score Following · Adaptive Music Control · Performance Analytics를  
합주 연습(개인 / 온라인 룸 / AI 세션 / 코칭)에 연결한 백엔드 프로토타입입니다.

---

## 기능 요약

| 기능 | 설명 | 상태 |
|------|------|------|
| Offline Ensemble Analysis | 파트별 WAV + MIDI → sync/리더/붕괴·회복 리포트 | Phase 1 ✅ |
| AI 개인 연습 + Sessionist | 내 연주 추적 + AI 다른 파트 스케줄/렌더 | Phase 2 ✅ |
| 실시간 코칭 tick + WebSocket | Drift/Breakdown 핵심 피드백만 | Phase 2 ✅ |
| Ensemble Room | 다중 참가 · 빈 파트 AI 채움 · 룸 분석 | Phase 3 ✅ |
| Sessionist 오디오 렌더 | MIDI/WAV 스템 합성 | Phase 3 ✅ |

상세 기술 설명: [`docs/TECHNOLOGY.md`](docs/TECHNOLOGY.md)  
아키텍처: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)  
API: [`docs/API.md`](docs/API.md)

---

## SORI 기술 → 코드 매핑 (한눈에)

| SORI 기술 | 이 레포에서의 역할 | 주요 코드 |
|-----------|-------------------|-----------|
| **Audio-to-MIDI / AMT** | 파트 오디오 → onset · local tempo | `sori_with/audio/processing.py`, `engines/part_understanding.py` |
| **Score Following** | MIDI 기준 bar/beat/section 정렬 | `sori_with/midi/score.py`, `engines/part_understanding.py` |
| **Adaptive Music Control** | AI Sessionist FOLLOW/ACCOMPANY, hold on low confidence | `engines/sessionist.py`, `audio/render.py` |
| **Performance Analytics** | Ensemble state · relation · coaching · report | `engines/ensemble_*.py`, `engines/coaching.py`, `pipeline/*` |

```text
파트 WAV/MIDI
    ↓
Part Understanding (onset, tempo, bar/beat)
    ↓
Ensemble Clock + Relations + State (stable/drift/breakdown/recovery)
    ├── Adaptive Sessionist (다른 파트 연주 스케줄 → WAV/MIDI)
    └── Coaching + Analytics Report
```

---

## 요구 사항

- Python **3.13**
- macOS / Linux

## 설치 & 실행

```bash
git clone <YOUR_REPO_URL> SORI.WITH
cd SORI.WITH

python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

uvicorn sori_with.api.main:app --reload --port 8000
```

- Swagger UI: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/health  

## 테스트

```bash
source .venv/bin/activate
pytest -q
```

합성 데이터(샘플 음원 불필요):

```bash
python - <<'PY'
from pathlib import Path
from sori_with.tools.synthetic import build_synthetic_session
print(build_synthetic_session(Path("data/synthetic_demo")))
PY
```

---

## 빠른 데모 (curl)

### 1) 오프라인 합주 분석

```bash
curl -s http://127.0.0.1:8000/api/v1/sessions/analyze/path \
  -H 'Content-Type: application/json' \
  -d '{
    "song_id":"demo",
    "midi_path":"data/synthetic_demo/score.mid",
    "parts":{
      "vocal":"data/synthetic_demo/vocal.wav",
      "guitar":"data/synthetic_demo/guitar.wav",
      "bass":"data/synthetic_demo/bass.wav",
      "drums":"data/synthetic_demo/drums.wav"
    },
    "tempo_bpm":120
  }'
```

### 2) 개인 연습 + AI Sessionist 렌더

```bash
curl -s http://127.0.0.1:8000/api/v1/practice/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "song_id":"demo",
    "midi_path":"data/synthetic_demo/score.mid",
    "user_part":"guitar",
    "user_wav_path":"data/synthetic_demo/guitar.wav",
    "sessionist_parts":["bass","drums"],
    "sessionist_mode":"follow",
    "tempo_bpm":120,
    "render_audio":true
  }'
```

### 3) Ensemble Room

```bash
# 방 생성 → join → score/audio path 등록 → analyze
curl -s http://127.0.0.1:8000/api/v1/rooms -H 'Content-Type: application/json' \
  -d '{"song_id":"band","room_name":"Campus","tempo_bpm":120}'
```

---

## 디렉터리 구조

```text
SORI.WITH/
├── README.md
├── LICENSE
├── requirements.txt
├── pyproject.toml
├── config/thresholds.yaml          # 분석·코칭 임계값
├── docs/
│   ├── TECHNOLOGY.md               # 기술별 구현 설명
│   ├── ARCHITECTURE.md             # 시스템 구조
│   └── API.md                      # API 목록
├── sori_with/
│   ├── api/                        # FastAPI (sessions, practice, rooms, ws)
│   ├── audio/                      # onset/tempo + Sessionist render
│   ├── midi/                       # score graph (MIDI)
│   ├── engines/                    # SORI 대응 핵심 엔진
│   ├── pipeline/                   # offline / practice 파이프라인
│   ├── models/schemas.py           # Pydantic 스키마
│   ├── realtime/hub.py             # WebSocket pub/sub
│   ├── storage/                    # in-memory session/room
│   └── tools/synthetic.py          # 테스트용 합성 합주 데이터
└── tests/
```

---

## 설계 원칙

1. **실시간 vs 사후 분리** — 실시간은 latency·보수적 판단, 사후는 전체 context로 재정렬  
2. **confidence 낮으면 동작 보류** — Sessionist `hold`, 코칭 미출력  
3. **비난형 피드백 금지** — `[현재 상태] + [기준 파트] + [실행 시점]`  
4. **MVP 범위** — 최대 4파트, 4/4, 70–160 BPM, 파트별 독립 입력 가정  

---

## 면책 / 관계

- 본 저장소는 SORI(sori-ai.com) 공개 기술 방향을 참고한 독립 프로토타입입니다.  
- SORI 공식 제품·모델 가중치·내부 API를 포함하지 않습니다.  

## License

MIT — [`LICENSE`](LICENSE)
