# SORI.WITH

**AI Ensemble Platform** — 합주 연습 · AI 세션 · 앙상블 분석 · 코칭을 한 흐름으로 묶은 **백엔드 + 모바일 UI** 프로토타입입니다.

SORI의 Audio-to-MIDI · Score Following · Adaptive Music Control · Performance Analytics 비전을  
**개인 연습 / 합주 룸 / AI Sessionist / 리포트** API와 화면으로 연결합니다.

> FastAPI 백엔드와 `web/` 앱 UI가 **같은 서버**에서 동작합니다.  
> `http://127.0.0.1:8000/` 으로 UI와 API를 함께 사용할 수 있습니다.

---

## 주요 기능

### 앱 UI (`web/`)

| 기능 | 설명 |
|------|------|
| **홈 · Practice / Join Ensemble** | 개인 연습, 오프라인·온라인 합주 진입 |
| **곡 선택 · Playlist** | 현재/과거 연습곡, YouTube 스타일 곡 추가 UI |
| **악기 · 대기실 · AI 빈자리 채우기** | 파트 선택, 룸 코드, 결석 파트를 AI로 다중 선택 채움 |
| **라이브 앙상블** | 피아노롤 시각화, 악기별 색 노트, 템포 알림, AI Sessionist 글로우 |
| **AI 앙상블 리포트** | 곡별 점수 발전, 회차 선택, 팀원(AI 대체 표시), 타임라인 · 다음 연습 제안 |
| **Profile** | 계정/빌링 설정형 레이아웃, 다크·라이트 모드, 알림 토글 |
| **스플래시 · 브랜딩** | SORI.WITH 워드마크, 첫 진입 스플래시 |

백엔드가 꺼져 있어도 UI는 **Demo Mode**로 플로우를 확인할 수 있습니다.

### 백엔드 API (`sori_with/`)

| 기능 | 설명 |
|------|------|
| **Offline Ensemble Analysis** | 파트 WAV + MIDI → sync / 리더 / Drift·Breakdown·Recovery 리포트 |
| **Score Following (DTW)** | onset ↔ score beat 정렬 + signed timing error |
| **AI Sessionist** | FOLLOW / ACCOMPANY, tempo transport, fail-safe hold |
| **개인 연습 파이프라인** | 유저 연주 + AI 다른 파트 스케줄 · WAV/MIDI 렌더 |
| **실시간 코칭 + WebSocket** | Drift/Breakdown 시 짧은 실행형 피드백 |
| **Ensemble Room** | 방 생성 · join · 빈 파트 AI fill · 룸 분석 |

상세 기술·한계: [`docs/TECHNOLOGY.md`](docs/TECHNOLOGY.md) · [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · [`docs/API.md`](docs/API.md)

---

## 한눈에 보는 구조

```text
파트 WAV / MIDI
       ↓
Onsets + Score Follower (DTW)
       ↓
Part Understanding → Ensemble Clock / Relations / State
       ├── Sessionist schedule → WAV / MIDI
       └── Coaching + Analytics Report
              ↕
        FastAPI + WebSocket
              ↕
     Mobile UI (web/index.html)
```

| SORI 기술 (비전) | 이 레포 구현 | 주요 코드 |
|------------------|--------------|-----------|
| Audio-to-MIDI | onset · IOI tempo (pitch 전사 없음) | `audio/processing.py` |
| Score Following | onset–score DTW + timing error | `engines/score_follower.py` |
| Adaptive Music Control | Sessionist content + tempo transport | `engines/sessionist.py` |
| Performance Analytics | sync / relation / coaching report | `engines/ensemble_*.py`, `coaching.py` |

---

## 요구 사항

- **Python 3.13**
- macOS / Linux

---

## 설치 & 실행 (프론트 + 백엔드 한 번에)

```bash
git clone https://github.com/shhong04/SORI.WITH.git
cd SORI.WITH

python3.13 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# (선택) 합성 데모 음원 생성
python - <<'PY'
from pathlib import Path
from sori_with.tools.synthetic import build_synthetic_session
print(build_synthetic_session(Path("data/synthetic_demo")))
PY

uvicorn sori_with.api.main:app --reload --host 0.0.0.0 --port 8000
```

| 주소 | 내용 |
|------|------|
| http://127.0.0.1:8000/ | **앱 UI** |
| http://127.0.0.1:8000/docs | Swagger API 문서 |
| http://127.0.0.1:8000/health | 헬스 체크 |
| http://127.0.0.1:8000/web/ | 정적 UI 에셋 |

폰에서 보려면 같은 Wi‑Fi의 `http://<Mac IP>:8000/` 또는 Cloudflare Tunnel 등으로 공개하면 됩니다.  
(Quick Tunnel은 프로세스가 켜져 있는 동안만 유효하며, URL은 재시작 시 바뀝니다.)

### 환경 변수 (요약)

| 변수 | 기본 | 설명 |
|------|------|------|
| `SORI_WITH_ENVIRONMENT` | `development` | `production`이면 로컬 path 분석 기본 비활성 |
| `SORI_WITH_ALLOW_PATH_ANALYZE` | (자동) | path 분석 엔드포인트 강제 |
| `SORI_WITH_CORS_ORIGINS` | localhost | 콤마 구분 origin |
| `SORI_WITH_MAX_UPLOAD_BYTES` | 52428800 | 업로드 최대 바이트 |

---

## 테스트

```bash
source .venv/bin/activate
pytest -q
```

---

## 시연: Offline Analyze (tempo / DTW / timing·relation)

합성 음원 생성 → 분석 → 터미널 요약 + HTML 결과:

```bash
# 1) 서버 없이 로컬 엔진만 (가장 빠름)
./scripts/demo_analyze.sh

# 2) 로컬 API에 MIDI+WAV 업로드 (Render와 동일 경로)
uvicorn sori_with.api.main:app --host 0.0.0.0 --port 8000
./scripts/demo_analyze.sh http://127.0.0.1:8000

# 3) 배포 Render에 업로드 시연
./scripts/demo_analyze.sh https://sori-with.onrender.com
```

결과:
- 터미널: tempo / alignment / timing·relation 요약
- `data/demo_analyze_summary.json` · `data/demo_analyze_full.json`
- 브라우저: 서버 켠 뒤 `http://127.0.0.1:8000/web/demo-analyze.html`
- 참여형 시연 안내(모니터용): `http://127.0.0.1:8000/web/demo-guide.html`
- Swagger 수동 시연: `/docs` → `POST /api/v1/sessions` → `POST /api/v1/sessions/{id}/analyze` (midi + vocal/guitar/bass/drums)

---

## 빠른 API 데모

> path 기반 분석은 **development**에서만 기본 활성입니다.

### 오프라인 합주 분석

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

### 개인 연습 + Sessionist

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

### Ensemble Room

```bash
curl -s http://127.0.0.1:8000/api/v1/rooms \
  -H 'Content-Type: application/json' \
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
├── config/thresholds.yaml
├── docs/                 # TECHNOLOGY · ARCHITECTURE · API
├── web/                  # 모바일 앱 UI (index.html + 워드마크)
│   ├── index.html
│   └── sori-wordmark*.png
├── sori_with/
│   ├── api/              # FastAPI routes + static UI mount
│   ├── audio/            # onset/tempo + Sessionist render
│   ├── midi/             # score graph
│   ├── engines/          # follower · ensemble · sessionist · coaching
│   ├── pipeline/         # offline / practice
│   ├── models/
│   ├── realtime/         # WebSocket hub
│   ├── storage/
│   └── tools/synthetic.py
└── tests/
```

---

## 현재 수준 

- **있음**: score-matched timing(P1), layered Sessionist(P2), Room/Practice API, 통합 모바일 UI
- **아직 없음**: pitch AMT, 본격 HMM/repeat graph, 영속 DB · auth · 큐 (P3)

설계 원칙: 실시간/사후 분리 · confidence 낮으면 hold · 비난형 피드백 금지 · MVP(최대 4파트, 4/4, 70–160 BPM)

---

## 면책

본 저장소는 SORI(sori-ai.com) 공개 기술 방향을 참고한 **독립 프로토타입**입니다.  
SORI 공식 제품·모델 가중치·내부 API를 포함하지 않습니다.

## License

MIT — [`LICENSE`](LICENSE)


