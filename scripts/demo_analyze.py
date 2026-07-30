#!/usr/bin/env python3.13
"""Demo: synthetic ensemble → offline analyze → print tempo / alignment / timing·relation.

Usage:
  # Local, no server (calls pipeline in-process)
  .venv/bin/python scripts/demo_analyze.py

  # Against running API (local or Render) — multipart upload path
  .venv/bin/python scripts/demo_analyze.py --base-url http://127.0.0.1:8000
  .venv/bin/python scripts/demo_analyze.py --base-url https://sori-with.onrender.com

  # Only regenerate WAVs/MIDI
  .venv/bin/python scripts/demo_analyze.py --generate-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_DATA = ROOT / "data" / "synthetic_demo"
DEFAULT_OUT = ROOT / "data" / "demo_analyze_summary.json"


def generate(out_dir: Path) -> dict[str, Path]:
    from sori_with.tools.synthetic import build_synthetic_session

    paths = build_synthetic_session(out_dir)
    print(f"[ok] synthetic → {out_dir}")
    for k, p in paths.items():
        print(f"     {k}: {p.name} ({p.stat().st_size} bytes)")
    return paths


def summarize(report: dict) -> dict:
    """Keep only the fields useful for a short live demo."""
    timeline = report.get("state_timeline") or []
    hist: dict[str, int] = {}
    for s in timeline:
        state = s.get("state") if isinstance(s, dict) else getattr(s, "state", None)
        if hasattr(state, "value"):
            state = state.value
        key = str(state or "?")
        hist[key] = hist.get(key, 0) + 1

    relations = report.get("relations") or []
    rel_rows = []
    for r in relations[:8]:
        if isinstance(r, dict):
            rel_rows.append(
                {
                    "from": r.get("source_part_id") or r.get("sourcePartId"),
                    "to": r.get("target_part_id") or r.get("targetPartId"),
                    "type": r.get("relation_type") or r.get("relationType"),
                    "strength": r.get("strength"),
                    "lagMs": r.get("lag_ms", r.get("lagMs")),
                    "confidence": r.get("confidence"),
                }
            )
        else:
            rel_rows.append(
                {
                    "from": r.source_part_id,
                    "to": r.target_part_id,
                    "type": getattr(r.relation_type, "value", r.relation_type),
                    "strength": r.strength,
                    "lagMs": r.lag_ms,
                    "confidence": r.confidence,
                }
            )

    return {
        "sessionId": report.get("session_id"),
        "songId": report.get("song_id"),
        "durationSec": report.get("duration_sec"),
        "parts": report.get("parts"),
        "tempo": report.get("ensemble_clock_summary"),
        "alignmentConfidence": report.get("part_alignment_confidence"),
        "timingDeviationMs": report.get("part_timing_deviation_ms"),
        "signedTimingDeviationMs": report.get("part_signed_timing_deviation_ms"),
        "stateHistogram": hist,
        "breakdown": report.get("breakdown_point"),
        "recovery": report.get("recovery_point"),
        "relations": rel_rows,
        "timingWindowsSample": (report.get("timing_windows") or [])[:6],
        "recommendedPractice": report.get("recommended_practice"),
        "evidenceNotes": report.get("evidence_notes"),
    }


def print_summary(summary: dict) -> None:
    print("\n======== SORI.WITH analyze demo ========")
    print(f"session : {summary.get('sessionId')}")
    print(f"parts   : {', '.join(summary.get('parts') or [])}")
    print(f"duration: {summary.get('durationSec'):.1f}s" if summary.get("durationSec") else "")

    tempo = summary.get("tempo") or {}
    print("\n[1] onset + IOI tempo → ensemble clock")
    print(f"    median_tempo     : {tempo.get('median_tempo')}")
    print(f"    reference_part   : {tempo.get('reference_part_id')}")
    print(f"    mean_stability   : {tempo.get('mean_stability')}")

    print("\n[2] onset–score DTW → alignment confidence")
    for part, conf in (summary.get("alignmentConfidence") or {}).items():
        print(f"    {part:8}  {conf:.3f}")

    print("\n[3] part timing / relation")
    print("    timing deviation (ms, abs):")
    for part, ms in (summary.get("timingDeviationMs") or {}).items():
        signed = (summary.get("signedTimingDeviationMs") or {}).get(part)
        signed_s = f"  signed={signed:+.1f}" if signed is not None else ""
        print(f"      {part:8}  {ms:.1f}{signed_s}")
    print("    state histogram:", summary.get("stateHistogram"))
    if summary.get("breakdown"):
        print("    breakdown:", summary["breakdown"])
    if summary.get("recovery"):
        print("    recovery :", summary["recovery"])
    print("    relations (sample):")
    for r in summary.get("relations") or []:
        print(
            f"      {r.get('from')} → {r.get('to')}  "
            f"type={r.get('type')}  strength={r.get('strength')}  lagMs={r.get('lagMs')}"
        )
    print("========================================\n")


def analyze_offline(data_dir: Path) -> dict:
    from sori_with.pipeline.offline_analysis import run_offline_ensemble_analysis

    report = run_offline_ensemble_analysis(
        session_id="demo_local",
        song_id="synthetic_demo",
        midi_path=data_dir / "score.mid",
        part_wavs={
            "vocal": data_dir / "vocal.wav",
            "guitar": data_dir / "guitar.wav",
            "bass": data_dir / "bass.wav",
            "drums": data_dir / "drums.wav",
        },
        tempo_bpm=120.0,
    )
    return report.model_dump(mode="json")


def analyze_api(base_url: str, data_dir: Path, timeout: float) -> dict:
    import httpx

    base = base_url.rstrip("/")
    with httpx.Client(base_url=base, timeout=timeout) as client:
        health = client.get("/health")
        health.raise_for_status()
        print(f"[ok] health {base} → {health.json()}")

        created = client.post(
            "/api/v1/sessions",
            json={
                "mode": "offline_analysis",
                "song_id": "synthetic_demo",
                "network_mode": "review",
            },
        )
        created.raise_for_status()
        session_id = created.json()["session_id"]
        print(f"[ok] session {session_id}")

        files = {
            "midi": ("score.mid", (data_dir / "score.mid").read_bytes(), "audio/midi"),
            "vocal": ("vocal.wav", (data_dir / "vocal.wav").read_bytes(), "audio/wav"),
            "guitar": ("guitar.wav", (data_dir / "guitar.wav").read_bytes(), "audio/wav"),
            "bass": ("bass.wav", (data_dir / "bass.wav").read_bytes(), "audio/wav"),
            "drums": ("drums.wav", (data_dir / "drums.wav").read_bytes(), "audio/wav"),
        }
        data = {"tempo_bpm": "120"}
        print("[..] uploading MIDI + 4 WAVs …")
        res = client.post(f"/api/v1/sessions/{session_id}/analyze", files=files, data=data)
        if res.status_code >= 400:
            raise SystemExit(f"analyze failed {res.status_code}: {res.text[:500]}")
        print(f"[ok] analyze {res.status_code}")
        return res.json()


def write_html(summary: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(summary, ensure_ascii=False, indent=2)
    path.write_text(
        f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>SORI.WITH · Analyze Demo</title>
  <style>
    :root {{ color-scheme: light; font-family: "IBM Plex Sans KR", "Noto Sans KR", sans-serif; }}
    body {{ margin: 0; background: #f3f1ec; color: #1a1a1a; }}
    main {{ max-width: 820px; margin: 0 auto; padding: 2rem 1.25rem 3rem; }}
    h1 {{ font-size: 1.35rem; margin: 0 0 .25rem; }}
    .sub {{ color: #555; margin-bottom: 1.5rem; font-size: .95rem; }}
    section {{ background: #fff; border: 1px solid #ddd; border-radius: 14px; padding: 1rem 1.1rem; margin-bottom: 1rem; }}
    h2 {{ font-size: .85rem; letter-spacing: .04em; text-transform: uppercase; color: #c23; margin: 0 0 .6rem; }}
    table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
    td, th {{ text-align: left; padding: .35rem .2rem; border-bottom: 1px solid #eee; }}
    pre {{ overflow: auto; font-size: .78rem; background: #faf8f5; padding: .8rem; border-radius: 8px; }}
    .pill {{ display: inline-block; background: #fde8e6; color: #a01812; padding: .15rem .5rem; border-radius: 999px; font-size: .8rem; margin-right: .35rem; }}
  </style>
</head>
<body>
<main>
  <h1>SORI.WITH · Offline Analyze Demo</h1>
  <p class="sub">onset + IOI tempo · onset–score DTW · part timing / relation</p>
  <section>
    <h2>Tempo (ensemble clock)</h2>
    <pre id="tempo"></pre>
  </section>
  <section>
    <h2>Alignment confidence (DTW)</h2>
    <table id="align"></table>
  </section>
  <section>
    <h2>Timing / state / relations</h2>
    <div id="states"></div>
    <table id="timing"></table>
    <pre id="relations"></pre>
  </section>
  <section>
    <h2>Full summary JSON</h2>
    <pre id="raw"></pre>
  </section>
</main>
<script>
const S = {body};
document.getElementById("tempo").textContent = JSON.stringify(S.tempo, null, 2);
document.getElementById("raw").textContent = JSON.stringify(S, null, 2);
const align = document.getElementById("align");
align.innerHTML = "<tr><th>part</th><th>confidence</th></tr>" +
  Object.entries(S.alignmentConfidence || {{}}).map(([k,v]) =>
    `<tr><td>${{k}}</td><td>${{Number(v).toFixed(3)}}</td></tr>`).join("");
const timing = document.getElementById("timing");
timing.innerHTML = "<tr><th>part</th><th>abs ms</th><th>signed ms</th></tr>" +
  Object.entries(S.timingDeviationMs || {{}}).map(([k,v]) => {{
    const s = (S.signedTimingDeviationMs || {{}})[k];
    return `<tr><td>${{k}}</td><td>${{Number(v).toFixed(1)}}</td><td>${{s == null ? "—" : Number(s).toFixed(1)}}</td></tr>`;
  }}).join("");
document.getElementById("states").innerHTML =
  Object.entries(S.stateHistogram || {{}}).map(([k,v]) =>
    `<span class="pill">${{k}}: ${{v}}</span>`).join("") +
  (S.breakdown ? `<p>breakdown: ${{JSON.stringify(S.breakdown)}}</p>` : "");
document.getElementById("relations").textContent = JSON.stringify(S.relations, null, 2);
</script>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> None:
    p = argparse.ArgumentParser(description="SORI.WITH offline analyze demo")
    p.add_argument(
        "--base-url",
        default="",
        help="API base (e.g. http://127.0.0.1:8000 or https://sori-with.onrender.com). "
        "Empty = in-process local pipeline (no server).",
    )
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--html", type=Path, default=ROOT / "web" / "demo-analyze.html")
    p.add_argument("--generate-only", action="store_true")
    p.add_argument("--skip-generate", action="store_true")
    p.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout seconds")
    args = p.parse_args()

    if not args.skip_generate:
        generate(args.data_dir)
    elif not (args.data_dir / "score.mid").exists():
        raise SystemExit(f"missing synthetic data at {args.data_dir} — run without --skip-generate")

    if args.generate_only:
        return

    if args.base_url:
        report = analyze_api(args.base_url, args.data_dir, args.timeout)
    else:
        print("[..] in-process offline analysis (no server)")
        report = analyze_offline(args.data_dir)

    summary = summarize(report)
    print_summary(summary)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    full = args.out.with_name("demo_analyze_full.json")
    full.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_html(summary, args.html)
    print(f"[ok] summary → {args.out}")
    print(f"[ok] full    → {full}")
    print(f"[ok] html    → {args.html}")
    if args.base_url:
        print(f"     open API docs: {args.base_url.rstrip('/')}/docs")
    else:
        print("     tip: serve UI and open /web/demo-analyze.html after starting uvicorn")


if __name__ == "__main__":
    main()
