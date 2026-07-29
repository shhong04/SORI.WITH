# GitHub에 올리기

## 1. 원격 저장소 생성
GitHub에서 New repository 생성 (README는 비워 두기 — 로컬 README 사용).

## 2. 로컬에서 푸시

```bash
cd /Users/diane/Desktop/SORI.WITH

git add .
git status   # .venv, data/reports, wav/mid 가 없는지 확인

git commit -m "$(cat <<'EOF'
Initial commit: SORI.WITH ensemble backend prototype

Offline analysis, AI Sessionist render, coaching, and ensemble rooms
with docs mapping SORI tech stacks to code modules.
EOF
)"

git branch -M main
git remote add origin git@github.com:<USER>/<REPO>.git
# 또는 https://github.com/<USER>/<REPO>.git

git push -u origin main
```

## 3. 푸시 전 체크
- [ ] `.venv/` 미포함
- [ ] `data/uploads`, `data/reports`, 대용량 wav 미포함
- [ ] `pytest -q` 통과
- [ ] README / docs 링크 깨지지 않음
