# SORI.WITH App UI

모바일 앱 프로토타입 (`index.html`). FastAPI가 루트(`/`)에서 함께 서빙합니다.

## 실행

저장소 루트에서:

```bash
source .venv/bin/activate
uvicorn sori_with.api.main:app --reload --host 0.0.0.0 --port 8000
```

- UI: http://127.0.0.1:8000/
- 에셋: `/web/sori-wordmark*.png`

## 주요 화면

- Practice / Join Ensemble · 곡·악기 선택 · 대기실 · AI 빈자리 채우기
- 라이브 피아노롤 · AI Sessionist 상태
- 곡별 리포트 · 회차 피드백 · 다음 연습 제안
- Playlist · Profile (다크/라이트 모드)

백엔드가 없으면 Demo Mode로 UI 플로우만 확인합니다.

## API 연동

| UI | API |
|----|-----|
| 연결 상태 | `GET /health` |
| 방 만들기 / 참가 | `POST /api/v1/rooms`, `.../join` |
| 개인 연습 | `POST /api/v1/practice/analyze` |

API 주소 변경(브라우저 콘솔):

```js
localStorage.setItem('SORI_API_BASE', 'http://127.0.0.1:8000')
```
