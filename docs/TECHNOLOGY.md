# SORI.WITH Technology Notes

SORI 네 기술 **비전**과 이 레포 **실제 구현**의 대응 관계입니다.
현재 코드는 제품급 MIR이 아니라 **아키텍처 시뮬레이터 + 휴리스틱 데모**입니다.

---

## 1. Audio-to-MIDI / AMT

### 목적 (비전)
라이브/녹음 오디오에서 합주 분석에 필요한 이벤트를 뽑는다.

### 현재 구현 (정직)
완전한 AMT가 아닙니다. **RMS energy flux onset + IOI tempo**만 있습니다.
pitch / chord / instrument-specific transcription은 **미구현**입니다.

### 구현 요약
1. WAV 로드 → mono · sample rate 통일 · peak normalize
2. 프레임 에너지 flux로 onset 검출
3. IOI로 local tempo curve 추정 (70–160 BPM 클램프)

### 코드

| 파일 | 역할 |
|------|------|
| [`sori_with/audio/processing.py`](../sori_with/audio/processing.py) | `load_mono`, `detect_onsets`, `estimate_tempo_curve` |
| [`sori_with/engines/part_understanding.py`](../sori_with/engines/part_understanding.py) | 파트별 `PartAnalysis` / `PartState` 생성 |

### 한계
- pitch confidence 등 placeholder 필드 가능 → 후속에서는 `None` 명시 권장
- 혼합 마이크 separation 없음 → 파트별 독립 WAV 가정
- 실제 밴드(보컬 sustain, distortion, bleed)에서는 onset 품질이 크게 떨어질 수 있음

---

## 2. Score Following

### 목적 (비전)
연주가 악보/MIDI의 어느 bar · beat · section인지 추정. 반복·생략·재진입 포함.

### 현재 구현 (P1)
onset 시각을 고정 tempo grid에 넣는 방식은 **폐기**했습니다.

1. 스코어 beat/event reference timeline 생성  
2. 연주 onset과 reference를 **DTW(스킵 허용)** 로 정렬  
3. `signed_error_ms = (onset − warped_score_time) × 1000` (양수 = late)  
4. `PartState.score_position` / confidence / `alignment_status`에 반영  
5. 리포트에 `part_signed_timing_deviation_ms`, `timing_windows`, `part_alignment_confidence` 출력  
6. `OnlineScoreFollower`는 슬라이딩 윈도우로 동일 DTW를 재실행하는 프로토타입

아직 없는 것: chroma 관측, 본격 HMM, repeat/skip graph 전이, neural AMT.

### 코드

| 파일 | 역할 |
|------|------|
| [`sori_with/engines/score_follower.py`](../sori_with/engines/score_follower.py) | `follow_score_offline`, `OnlineScoreFollower` |
| [`sori_with/engines/part_understanding.py`](../sori_with/engines/part_understanding.py) | 정렬 결과를 PartState에 연결 |
| [`sori_with/midi/score.py`](../sori_with/midi/score.py) | `ScoreGraph` / beat grid |

### 관련 analytics 개선 (P1)
- Ensemble spread: score-matched signed error의 std  
- Deviating parts: **시간 창 로컬** 편차  
- Relations: 윈도우 단위, 방향 충돌 쌍 제거  
- State: hysteresis + recovery 조건 강화

---

## 3. Adaptive Music Control (AI Sessionist)

### 목적 (비전)
부족한 파트를 사용자 tempo/위치에 맞춰 조절하는 AI 세션.

### 현재 구현 (P2) — 4계층
1. **Score content** — 역할 pitch band의 MIDI 노트 우선, 부족하면 pattern fallback  
2. **Transport** — `build_transport_map`: score time → performance time **누적 tempo 적분**  
3. **Scheduler** — `plan_sessionist_schedule` + `schedule_lookahead`  
4. **Live control** — `LiveSessionistController`  
   - confidence 낮음 → `hold` / phrase maintain / safe-boundary `repeat`  
   - 회복 시 downbeat `reenter`  
5. **Renderer** — `audio/render.py` (play/fill/repeat/reenter)

아직 없는 것: chord-aware voicing, audio time-stretch of recorded stems, true phase-locked audio buffer.

| 모드 | 동작 |
|------|------|
| `FOLLOW` | tempo 추종 강함 |
| `ACCOMPANY` | 추종 + phrase-end fill |
| `LEAD` / `INTERACT` | 스키마·약한 추종 계수 |

코드: `engines/sessionist.py`, `audio/render.py`

---

## 4. Performance Analytics

### 목적 (비전)
Who Led/Followed, Breakdown·Recovery, 합주 준비도, 실행 가능 코칭.

### 현재 구현 (정직)
- Clock: score-matched phase 우선 + role-prior reference  
- Relations: **윈도우별** probable influence (인과 단정 금지)  
- Breakdown/Recovery: score-matched error spread + hysteresis  
- Deviating parts: **로컬 시간 창** 기준  
- Coaching: 규칙 + cooldown (정렬 confidence에 종속)
---

## 우선 로드맵

| 우선순위 | 내용 |
|----------|------|
| **P0** | README 정직화, path 가드, 업로드 제한, 예외 비노출, CORS, cleanup, 테스트 격리 ✅ |
| **P1** | ScoreFollower DTW + score-matched signed deviation + windowed analytics ✅ |
| **P2** | Sessionist 재설계 (content / transport / scheduler / live fail-safe) ✅ |
| **P3** | DB / auth / queue / WebRTC 제품화 |

관련: [`ARCHITECTURE.md`](ARCHITECTURE.md), [`API.md`](API.md)
