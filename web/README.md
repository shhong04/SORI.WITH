# SORI.WITH App Prototype

다크·코랄 테마 모바일 프로토타입 (`index.html`).  
FastAPI가 `/` 로 서빙하며, 백엔드가 꺼져 있으면 Demo Mode로 동작합니다.

## 실행

```bash
# 저장소 루트
source .venv/bin/activate
uvicorn sori_with.api.main:app --reload --port 8000
```

브라우저: http://127.0.0.1:8000/

합성 데모 데이터가 없으면:

```bash
python - <<'PY'
from pathlib import Path
from sori_with.tools.synthetic import build_synthetic_session
print(build_synthetic_session(Path("data/synthetic_demo")))
PY
```

## 백엔드 연동

| UI | API |
|----|-----|
| Backend badge | `GET /health` |
| 방 만들기 | `POST /api/v1/rooms` + host `.../join` |
| 방 참가 | 코드 → room list 매칭 → `POST /rooms/{id}/join` (`user_id`,`part_id`) |
| 개인 연습 분석 | `POST /api/v1/practice/analyze` |

API 주소를 바꾸려면 브라우저 콘솔:

```js
localStorage.setItem('SORI_API_BASE', 'http://127.0.0.1:8000')
```
