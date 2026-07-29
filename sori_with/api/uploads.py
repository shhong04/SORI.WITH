"""Upload and path safety helpers for the API layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile

from sori_with.config import ROOT, Settings, get_settings

ANALYSIS_FAILED = {
    "code": "ANALYSIS_FAILED",
    "message": "오디오 분석에 실패했습니다.",
}
UPLOAD_TOO_LARGE = {
    "code": "UPLOAD_TOO_LARGE",
    "message": "업로드 파일이 허용 크기를 초과했습니다.",
}
INVALID_UPLOAD = {
    "code": "INVALID_UPLOAD",
    "message": "지원하지 않는 파일 형식입니다.",
}
PATH_NOT_ALLOWED = {
    "code": "PATH_NOT_ALLOWED",
    "message": "허용되지 않은 파일 경로입니다.",
}
PATH_ENDPOINT_DISABLED = {
    "code": "PATH_ENDPOINT_DISABLED",
    "message": "로컬 경로 분석은 development 환경에서만 사용할 수 있습니다.",
}


def require_path_analyze_enabled(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.path_analyze_enabled:
        raise HTTPException(status_code=403, detail=PATH_ENDPOINT_DISABLED)


def allowed_path_roots(settings: Settings | None = None) -> list[Path]:
    settings = settings or get_settings()
    roots = [settings.data_dir.resolve(), ROOT.resolve()]
    # pytest / local scratch paths — never in production
    if not settings.is_production:
        roots.append(Path(tempfile.gettempdir()).resolve())
    return roots


def resolve_allowed_path(path_str: str, *, settings: Settings | None = None) -> Path:
    """Resolve a user-supplied path and reject traversal outside data/project roots."""
    settings = settings or get_settings()
    raw = Path(path_str).expanduser()
    resolved = (Path.cwd() / raw).resolve() if not raw.is_absolute() else raw.resolve()
    for root in allowed_path_roots(settings):
        try:
            resolved.relative_to(root)
            break
        except ValueError:
            continue
    else:
        raise HTTPException(status_code=400, detail=PATH_NOT_ALLOWED)
    if not resolved.exists():
        raise HTTPException(status_code=400, detail="file not found")
    return resolved


async def read_upload_limited(
    upload: UploadFile,
    *,
    max_bytes: int | None = None,
    settings: Settings | None = None,
) -> bytes:
    settings = settings or get_settings()
    limit = max_bytes if max_bytes is not None else settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail=UPLOAD_TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


def validate_midi_bytes(data: bytes) -> None:
    if len(data) < 14 or data[:4] != b"MThd":
        raise HTTPException(status_code=400, detail=INVALID_UPLOAD)


def validate_wav_bytes(data: bytes) -> None:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise HTTPException(status_code=400, detail=INVALID_UPLOAD)
