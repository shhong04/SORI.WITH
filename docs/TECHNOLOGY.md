# SORI.WITH Technology Notes

SORI 네 기술과 이 레포 구현의 대응 관계입니다.

---

## 1. Audio-to-MIDI / AMT (Automatic Music Transcription)

### 목적
라이브(또는 녹음) 오디오에서 **합주 분석에 필요한 이벤트**를 뽑는다.  
MVP에서는 완전한 채보보다 **onset · beat · tempo**를 우선한다.

### 구현 요약
1. WAV 로드 → mono · sample rate 통일 · peak normalize  
2. 프레임 에너지 flux로 onset 검출  
3. IOI(onset 간격)로 local tempo curve 추정 (70–160 BPM 클램프)

### 코드

| 파일 | 역할 |
|------|------|
| [`sori_with/audio/processing.py`](../sori_with/audio/processing.py) | `load_mono`, `detect_onsets`, `estimate_tempo_curve` |
| [`sori_with/engines/part_understanding.py`](../sori_with/engines/part_understanding.py) | 파트별 `PartAnalysis` / `PartState` 생성 |

### 핵심 함수 흐름

```text
wav
 → load_mono()
 → detect_onsets()          # energy flux + percentile threshold
 → estimate_tempo_curve()   # IOI → BPM, smoothing
 → PartState(timestamp, tempo, score_position, confidence)
```

### 한계 (의도된 MVP 제약)
- 다성 pitch / velocity / pedal 정밀 전사는 미구현 (placeholder accuracy 사용처 있음)
- 혼합 마이크 source separation 없음 → **파트별 독립 WAV** 가정
- 드럼은 onset 리듬 중심으로 충분, 보컬 pitch contour는 후속 과제

---

## 2. Score Following

### 목적
연주 이벤트가 **악보/MIDI의 어느 bar · beat · section**인지 추정한다.  
반복·생략·재진입은 상태 플래그로 확장 가능하도록 스키마를 열어 두었다.

### 구현 요약
1. MIDI → `ScoreGraph` (tempo, time signature, note events, section markers)  
2. onset 시각 `t` → `bar_beat_at(t)`, `section_at(t)`  
3. `ScorePosition` + `alignment_status` (`aligned` / `lost` / …)

### 코드

| 파일 | 역할 |
|------|------|
| [`sori_with/midi/score.py`](../sori_with/midi/score.py) | `load_midi_score`, `synthesize_click_midi`, `ScoreGraph` |
| [`sori_with/engines/part_understanding.py`](../sori_with/engines/part_understanding.py) | onset → score position 매핑 |
| [`sori_with/models/schemas.py`](../sori_with/models/schemas.py) | `ScorePosition`, `AlignmentStatus` |

### 설계 메모
- 초기 정렬은 **고정 tempo grid + MIDI 이벤트** 기반 (online DTW/HMM은 인터페이스 확장 지점)
- 한 파트 오류가 전체를 흔들지 않도록 Ensemble Clock에서 **역할 prior 가중** 사용

---

## 3. Adaptive Music Control (AI Sessionist)

### 목적
부족한 파트를 **고정 MR 재생이 아니라**, 사용자 tempo/위치에 맞춰 조절하는 AI 세션으로 채운다.

### 모드 (명세 정합)
| 모드 | 동작 |
|------|------|
| `FOLLOW` | 사용자 tempo를 강하게 추종 |
| `ACCOMPANY` | 추종 + phrase-end fill |
| `LEAD` / `INTERACT` | 스키마·훅만 준비 (MVP 후순위) |

### 구현 요약
1. 역할별 리듬 패턴(킥/스네어, 베이스 루트 등)을 bar grid에 배치  
2. 사용자 tempo curve로 스케줄 시간축 stretch + smoothing  
3. `confidence < threshold` → `hold` (잘못된 자동 전환 방지)  
4. 스케줄 → 단순 합성기로 **WAV/MIDI 렌더**

### 코드

| 파일 | 역할 |
|------|------|
| [`sori_with/engines/sessionist.py`](../sori_with/engines/sessionist.py) | `plan_sessionist_schedule`, `control_from_live_tick` |
| [`sori_with/audio/render.py`](../sori_with/audio/render.py) | `render_schedule_to_audio`, `write_midi_from_schedule`, `render_sessionist_bundle` |
| [`sori_with/pipeline/practice.py`](../sori_with/pipeline/practice.py) | 개인 연습 파이프라인에서 Sessionist 호출 |
| [`sori_with/api/routes/rooms.py`](../sori_with/api/routes/rooms.py) | 룸 분석 시 빈 파트 AI fill |

### 제어 출력 예 (`SessionistAction`)

```json
{
  "timestamp": 12.4,
  "role": "bass",
  "mode": "follow",
  "target_bar": 24,
  "target_beat": 1.0,
  "target_tempo": 108.4,
  "action": "play",
  "pitch": 36,
  "confidence": 0.95
}
```

---

## 4. Performance Analytics & Coaching

### 목적
파트 간 timing 관계와 합주 상태를 분석하고,  
**합주 전체에 영향 큰 문제만** 짧게 코칭한 뒤 사후 리포트를 만든다.

### Ensemble 엔진

| 엔진 | 질문 | 코드 |
|------|------|------|
| Ensemble Clock | 팀이 따르는 공통 tempo/beat는? | `engines/ensemble_clock.py` |
| Relationship | Who led / followed / lagged? | `engines/ensemble_relationship.py` |
| State | stable / drift / breakdown / recovery | `engines/ensemble_state.py` |
| Coaching | 지금 누구에게 무엇을 말할까? | `engines/coaching.py` |

### 상태 정의
- **STABLE** — spread가 허용 범위  
- **DRIFT** — 점진적 벌어짐, 합주는 유지  
- **BREAKDOWN** — 기준 분리, 흐름 붕괴  
- **RECOVERY** — downbeat/tempo 재수렴  

### 코칭 규칙
1. STABLE이면 말하지 않음  
2. 자연 회복 확률이 높고 spread가 작으면 보류  
3. cooldown (기본 4s)  
4. 문장: `[상태] + [기준 파트] + [다음 마디/박 실행]`  
5. 비난형 금지 (“네가 틀림” X)

### 리포트 파이프라인
- Offline: [`pipeline/offline_analysis.py`](../sori_with/pipeline/offline_analysis.py)  
- Practice: [`pipeline/practice.py`](../sori_with/pipeline/practice.py)  
- 임계값: [`config/thresholds.yaml`](../config/thresholds.yaml)

---

## 5. Realtime / Ensemble Room

### WebSocket Hub
[`sori_with/realtime/hub.py`](../sori_with/realtime/hub.py) — 세션/룸별 in-process pub/sub

| 채널 | 경로 | 이벤트 예 |
|------|------|-----------|
| Session live | `WS /api/v1/ws/sessions/{id}` | `live_tick`, coaching |
| Room | `WS /api/v1/ws/rooms/{id}` | `member_joined`, `room_analyzed` |

### Ensemble Room 흐름
```text
create room → join(part) → upload score/audio
 → start → analyze
    ├ human parts
    └ missing parts ← Sessionist render fill
 → dashboard / report
```

코드: [`api/routes/rooms.py`](../sori_with/api/routes/rooms.py), [`storage/rooms.py`](../sori_with/storage/rooms.py)

---

## 6. 테스트로 검증하는 것

| 테스트 | 검증 |
|--------|------|
| `tests/test_offline_analysis.py` | 합성 합주 → clock/state/deviation |
| `tests/test_api.py` | Phase1 HTTP API |
| `tests/test_phase2.py` | Sessionist · coaching · practice · WS tick |
| `tests/test_phase3.py` | render WAV · room join/analyze/WS |

합성 픽스처: [`tools/synthetic.py`](../sori_with/tools/synthetic.py) (후반 bass delay로 drift 유도)

---

## 7. 공식 SORI와의 차이

| 항목 | 공식 SORI (공개 기준) | 이 레포 |
|------|----------------------|---------|
| 모델 | 상용/연구 모델, Leaderboard 수치 | 경량 DSP + 규칙 엔진 프로토타입 |
| 입력 | 공연·스트리밍 제품화 | 파일/시뮬 tick 중심 |
| 목적 | 제품 | 교육·해커톤·아키텍처 검증 |

SORI 브랜드·가중치·비공개 API는 포함되지 않습니다.
