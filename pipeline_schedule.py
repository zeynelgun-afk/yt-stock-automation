"""Resolve scheduled modes using the original run, never the runner's clock."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

RECAP_CRONS = {"5 20 * * 1-5": 20, "5 21 * * 1-5": 21}
SCHEDULE_MODES = {
    "30 12 * * 1-5": "shorts",
    "0 17 * * 1-5": "shorts",
    "30 0 * * 2-6": "shorts",
    "35 13 * * 1-5": "event-shorts",
    "0 15 * * 0": "analytics",
}


def resolve_mode(event_name: str, event: dict, run_created_at: str = "") -> str:
    if event_name == "workflow_dispatch":
        mode = event.get("inputs", {}).get("mode") or "shorts"
        if mode not in ("shorts", "long", "analytics", "comments"):
            raise ValueError("Unsupported manual pipeline mode")
        return mode
    if event_name != "schedule":
        raise ValueError("Unsupported pipeline event")
    cron = event.get("schedule", "")
    if cron in RECAP_CRONS:
        created = datetime.fromisoformat(run_created_at.replace("Z", "+00:00"))
        if created.tzinfo is None:
            raise ValueError("Run creation time must include a timezone")
        created = created.astimezone(timezone.utc)
        # Schedule events identify the cron, not the nominal occurrence time.
        # Recover its latest weekday occurrence preceding original run creation.
        # This tolerates queue delays across midnight; reruns use the same origin.
        scheduled = created.replace(hour=RECAP_CRONS[cron], minute=5, second=0, microsecond=0)
        if scheduled > created:
            scheduled -= timedelta(days=1)
        while scheduled.weekday() >= 5:
            scheduled -= timedelta(days=1)
        return "long" if scheduled.astimezone(ZoneInfo("America/New_York")).hour == 16 else "skip"
    if cron not in SCHEDULE_MODES:
        raise ValueError("Unknown pipeline cron")
    return SCHEDULE_MODES[cron]


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    mode = resolve_mode(os.environ["GITHUB_EVENT_NAME"], event, os.getenv("RUN_CREATED_AT", ""))
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"mode={mode}\ntrend_date={datetime.now(timezone.utc):%Y-%m-%d}\n")
    print(f"Resolved mode: {mode}")


if __name__ == "__main__":
    main()
