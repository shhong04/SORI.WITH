# Architecture

## 전체 파이프라인

```text
[Client]
  WAV / MIDI upload · live tick · room join
           │
           ▼
[FastAPI]  sori_with/api/main.py
  /sessions  /practice  /rooms  /ws/*
           │
           ▼
[Pipelines]
  offline_analysis.py    practice.py
           │
           ├─ audio/processing.py      (onset, tempo)
           ├─ midi/score.py            (score graph)
           ├─ engines/part_understanding.py
           ├─ engines/ensemble_clock.py
           ├─ engines/ensemble_relationship.py
           ├─ engines/ensemble_state.py
           ├─ engines/sessionist.py
           ├─ engines/coaching.py
           └─ audio/render.py          (WAV/MIDI out)
           │
           ▼
[Storage]  memory.py · rooms.py   (MVP in-memory)
[Realtime] hub.py                 (WebSocket fan-out)
[Config]   config/thresholds.yaml
```

## 레이어 책임

| Layer | 책임 | 비책임 |
|-------|------|--------|
| API | HTTP/WS 계약, 업로드, 상태코드 | 음악 판단 |
| Pipeline | 유스케이스 오케스트레이션 | 임계값 하드코딩 |
| Engines | 음악 상태·제어·코칭 결정 | DB/네트워크 |
| Audio/MIDI | 신호·스코어 I/O | 제품 정책 |
| Storage | 세션/룸/리포트 보관 | 영속 DB (MVP) |

## 데이터 모델 (핵심)

정의 위치: `sori_with/models/schemas.py`

- `PartState` — 한 파트의 순간 상태  
- `EnsembleClock` — 공통 tempo / bar / reference part  
- `EnsembleState` — stable·drift·breakdown·recovery  
- `EnsembleRelation` — lead/follow/lag  
- `SessionistAction` — AI 세션 연주 명령  
- `CoachingEvent` — 전달 가능한 코칭 메시지  
- `AnalysisReport` / `PracticeReport` — 사후 산출물  
- `EnsembleRoom` / `RoomMember` — 온라인 합주방  

## 설정

`config/thresholds.yaml`

- onset percentile, min gap  
- stable/drift/breakdown spread (ms)  
- role prior (drums > bass > …)  
- coaching deviation / cooldown  

코드 로드: `sori_with/config.py` → `get_thresholds()`

## 확장 포인트

1. **Online DTW / HMM Score Follower** — `midi/score.py` + part engine 교체  
2. **Neural AMT** — `detect_onsets`를 모델 inference로 대체  
3. **WebRTC transport** — room 오디오를 파일 업로드 대신 스트림으로  
4. **DB** — `storage/memory.py`를 Postgres/Redis로 교체  
5. **LLM copy** — `coaching.py`는 구조화 evidence만, 문장 생성만 LLM  

## 배포 메모 (현재)

- 단일 프로세스 in-memory → 멀티 워커 시 룸/세션 공유 불가  
- 업로드는 `data/uploads`, 리포트는 `data/reports` (gitignore)  
- 프로덕션 전에는 인증·용량 제한·CORS 재설정 필요  
