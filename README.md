# SORI.WITH

**AI Ensemble Platform 아키텍처 시뮬레이터** — SORI의 Audio-to-MIDI · Score Following · Adaptive Music Control · Performance Analytics **제품 비전**을  
합주 연습 API 흐름(개인 / 온라인 룸 / AI 세션 / 코칭)으로 연결한 **백엔드 프로토타입**입니다.

> **현재 상태 (정직한 요약)**  
> FastAPI 프로토타입 + **P1 score-matched timing** + **P2 layered Sessionist**.  
> pitch AMT, 본격 HMM/repeat graph, 영속 DB/auth는 아직 없습니다.
---

## 기능 요약

| 기능 | 설명 | 실제 수준 |
|------|------|-----------|
| Offline Ensemble Analysis | 파트 WAV + MIDI → 리포트 API | **API + score-matched timing (P1)** |
| Score Following (DTW) | onset ↔ score beat/event 정렬 + signed error | **P1 offline / online stub** |
| AI 개인 연습 + Sessionist | score content + tempo transport + fail-safe live control | **P2 Sessionist** |
| 실시간 코칭 tick + WebSocket | Drift/Breakdown 규칙 기반 피드백 | **policy skeleton** |
| Ensemble Room | 다중 참가 · 빈 파트 AI fill · 룸 분석 | **API demo** |
| Sessionist 오디오 렌더 | schedule → MIDI/WAV 스템 | **renderer** |

상세·한계: [`docs/TECHNOLOGY.md`](docs/TECHNOLOGY.md)  
아키텍처: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)  
API: [`docs/API.md`](docs/API.md)

---

## SORI 기술 → 코드 매핑 (한눈에)

| SORI 기술 (비전) | 이 레포의 실제 구현 | 주요 코드 |
|------------------|---------------------|-----------|
| **Audio-to-MIDI / AMT** | onset · IOI tempo (pitch 전사 없음) | `audio/processing.py`, `engines/part_understanding.py` |
| **Score Following** | onset–score DTW 정렬 + signed timing error (P1) | `engines/score_follower.py`, `part_understanding.py` |
| **Adaptive Music Control** | content→transport→scheduler + live fail-safe (P2) | `engines/sessionist.py`, `audio/render.py` |
| **Performance Analytics** | score-matched spread / windowed relation / coaching | `engines/ensemble_*.py`, `engines/coaching.py` |

```text
파트 WAV/MIDI
    ↓
Onsets + Offline ScoreFollower (DTW)
    ↓
Part Understanding (matched bar/beat, signed error ms)
    ↓
Ensemble Clock + windowed Relations + State (hysteresis)
    ├── Sessionist pattern schedule → WAV/MIDI
    └── Coaching + Analytics Report
```

다음 스프린트(P3): DB/auth/queue 등 제품화.  
P2: Sessionist는 MIDI role content(가능 시) + 누적 tempo transport + look-ahead/live fail-safe.---

## 요구 사항

- Python **3.13** (프로토타입 고정; 향후 MIR 라이브러리 도입 시 3.11/3.12 재검토 가능)
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

### 환경 변수 (요약)

| 변수 | 기본 | 설명 |
|------|------|------|
| `SORI_WITH_ENVIRONMENT` | `development` | `production`이면 로컬 path 분석 기본 비활성 |
| `SORI_WITH_ALLOW_PATH_ANALYZE` | (자동) | `true`/`false`로 path 엔드포인트 강제 |
| `SORI_WITH_CORS_ORIGINS` | localhost 5173/3000 | 콤마 구분 origin |
| `SORI_WITH_MAX_UPLOAD_BYTES` | 52428800 | 업로드 최대 바이트 |
| `SORI_WITH_KEEP_UPLOAD_ARTIFACTS` | `false` | `true`면 업로드 workdir 유지 |

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

> `/sessions/analyze/path` 및 practice path API는 **development**에서만 기본 활성입니다.  
> 경로는 프로젝트/`data` 이하로 제한됩니다.

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
│   ├── TECHNOLOGY.md               # 기술별 구현·한계
│   ├── ARCHITECTURE.md             # 시스템 구조
│   └── API.md                      # API 목록
├── sori_with/
│   ├── api/                        # FastAPI (sessions, practice, rooms, ws)
│   ├── audio/                      # onset/tempo + Sessionist render
│   ├── midi/                       # score graph (MIDI)
│   ├── engines/                    # 휴리스틱 엔진
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
