# SORI.WITH Visual Demo

비전문가용 스토리보드 UI입니다. 백엔드가 없어도 60초 시나리오가 재생되고, API가 켜져 있으면 리포트·라이브 코칭을 붙입니다.

## 실행

터미널 1 — 백엔드 (선택, 있으면 리포트/코칭 연동):

```bash
cd ..
source .venv/bin/activate
uvicorn sori_with.api.main:app --reload --port 8000
```

터미널 2 — 프론트:

```bash
cd web
npm install
npm run dev
```

브라우저: http://127.0.0.1:5173

- API 기본 주소: `http://127.0.0.1:8000` (`VITE_API_BASE`로 변경 가능)
- Vite는 `/api`, `/health`를 8000으로 프록시합니다.

## 화면

1. **혼자 연습 + AI 세션** — AI 합류 → 흔들림 → 코칭 → 회복 스토리
2. **합주방 한눈에** — 파트별 앞/뒤(빠르/늦음) 위치
3. **리포트** — 백엔드 분석이 있으면 실제 수치, 없으면 데모 요약

조작: 재생/일시정지, AI ON/OFF, 템포 흔들기 슬라이더, 타임라인 시크

## 빌드

```bash
npm run build
npm run preview
```
