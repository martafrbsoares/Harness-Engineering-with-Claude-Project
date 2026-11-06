"""system-5: claims -> shift monitor bridge.

system-1 (claims_intake)         produces runs/<id>/{queues,escalations}.jsonl
system-4 (shift_monitor)         stores them in the warm tier and keeps a 5 KB hot state
system-3 (ecommerce_team_config) supplies CLAUDE.md + @-imported standards as standing context

Run with system-4's interpreter (it has shift_monitor and pydantic installed):
    ..\\system-4\\.venv\\Scripts\\python.exe bridge.py            # offline
    ..\\system-4\\.venv\\Scripts\\python.exe bridge.py --live     # needs ANTHROPIC_API_KEY
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
S1, S3, S4 = (ROOT.parent / f"system-{n}" for n in (1, 3, 4))
sys.path[:0] = [str(S3), str(S4)]

from ecommerce_team_config.imports import find_imports, unresolved_imports  # noqa: E402
from shift_monitor import pipeline  # noqa: E402
from shift_monitor.client import (  # noqa: E402
    AnthropicClaudeClient,
    ClaudeClient,
    Message,
    RecordedClaudeClient,
)
from shift_monitor.state import HotState  # noqa: E402
from shift_monitor.warm import WarmStore  # noqa: E402


def latest_run(runs_dir: Path) -> Path:
    runs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    if not runs:
        raise SystemExit(f"no system-1 runs under {runs_dir}")
    return runs[-1]


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def claims_to_defects(run: Path) -> list[dict[str, str]]:
    """system-1 outcomes -> system-4 warm-tier rows (routed = claim_type, escalated = 'escalation')."""
    ts = datetime.strptime(run.name, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    stamp = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: list[dict[str, str]] = []
    for queue in sorted((run / "queues").glob("*.jsonl")):
        for c in _read_jsonl(queue):
            rows.append(
                {
                    "id": str(c["claim_id"]),
                    "ts": stamp,
                    "shift": "A",
                    "component": str(c.get("claim_type", queue.stem)),
                    "severity": str(c.get("severity", "unknown")),
                    "description": str(c.get("claim_summary", ""))[:300],
                }
            )
    for e in _read_jsonl(run / "escalations.jsonl"):
        rows.append(
            {
                "id": str(e["claim_id"]),
                "ts": stamp,
                "shift": "A",
                "component": "escalation",
                "severity": "high",
                "description": f"{e.get('reason', '')} | root cause: {e.get('root_cause', '')}"[:300],
            }
        )
    return rows


def team_conventions(claude_md: Path) -> str:
    """system-3: CLAUDE.md with its @-imports inlined, as standing context."""
    missing = unresolved_imports(claude_md, repo_root=claude_md.parent)
    if missing:
        raise SystemExit(f"unresolved CLAUDE.md imports: {missing}")
    parts = [claude_md.read_text(encoding="utf-8")]
    for rel in find_imports(claude_md):
        parts.append((claude_md.parent / rel).read_text(encoding="utf-8"))
    return "\n\n".join(parts)


class ConventionsClient:
    """Prepends system-3 conventions to every prompt; the hot state itself stays under budget."""

    def __init__(self, inner: ClaudeClient, conventions: str) -> None:
        self.inner = inner
        self.conventions = conventions

    def complete(self, messages: list[Message]) -> Message:
        head = f"# Team conventions (system-3)\n\n{self.conventions}\n\n---\n\n"
        first = Message(role=messages[0].role, content=head + messages[0].content)
        return self.inner.complete([first, *messages[1:]])


def offline_response(rows: list[dict[str, str]]) -> str:
    """Deterministic stand-in for the model, derived from the real claim data."""
    esc = [r for r in rows if r["component"] == "escalation"]
    rate = len(esc) / len(rows) if rows else 0.0
    update = {
        "current_shift_summary": (
            f"Claims batch: {len(rows)} claims, {len(esc)} escalated "
            f"({rate:.0%}), {len(rows) - len(esc)} routed."
        ),
        "active_alerts": (
            [f"escalation rate {rate:.0%} - review the backstop root cause"] if rate > 0.25 else []
        ),
        "threshold_statuses": {"escalation_rate": "ALARM" if rate > 0.25 else "OK"},
    }
    return f"## Updated hot state proposal\n```json\n{json.dumps(update)}\n```\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, default=None, help="system-1 run dir (default: latest)")
    ap.add_argument("--live", action="store_true", help="call the Anthropic API")
    args = ap.parse_args()

    run = args.run or latest_run(S1 / "runs")
    rows = claims_to_defects(run)

    data = ROOT / "data"
    warm = WarmStore(data / "warm.sqlite")
    warm.initialize()
    warm.insert_many(rows)

    hot = data / "hot_state.json"
    if not hot.exists():
        HotState(
            recent_defect_hashes=[],
            current_shift_summary="(no prior shift)",
            active_alerts=[],
            threshold_statuses={},
        ).write_atomic(hot)

    inner: ClaudeClient = (
        AnthropicClaudeClient() if args.live else RecordedClaudeClient([offline_response(rows)])
    )
    client = ConventionsClient(inner, team_conventions(S3 / "CLAUDE.md"))
    result = pipeline.run_shift(
        shift_id="A",
        client=client,
        warm=warm,
        hot_state_path=hot,
        scratchpad_path=data / "shift_scratchpad.jsonl",
        since_ts="1970-01-01T00:00:00Z",
    )
    print(f"system-1 run {run.name}: {len(rows)} claims -> warm tier ({warm.count()} rows total)")
    print(f"system-4 shift {result.shift_id}: {result.new_defect_count} new, {result.summary}")
    print(f"hot_state.json: {hot.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
