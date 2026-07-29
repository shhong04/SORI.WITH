# Engines code map

| Module | SORI concept | Entry points |
|--------|--------------|--------------|
| `score_follower.py` | Score Following (onset–score DTW) | `follow_score_offline()`, `OnlineScoreFollower` |
| `part_understanding.py` | AMT-lite + Following | `analyze_part()` |
| `ensemble_clock.py` | shared musical time | `estimate_ensemble_clock()` |
| `ensemble_relationship.py` | lead/follow analytics | `estimate_relations()`, `timing_deviation_ms()`, `signed_timing_deviation_ms()` |
| `ensemble_state.py` | stable/drift/breakdown/recovery | `build_state_timeline()`, `build_events()` |
| `sessionist.py` | Adaptive Music Control | `plan_sessionist_schedule()`, `control_from_live_tick()` |
| `coaching.py` | Performance feedback policy | `decide_coaching()` |

See [`../docs/TECHNOLOGY.md`](../docs/TECHNOLOGY.md) for full explanations.
