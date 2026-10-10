"""Persist learning even on partial failure, then fail the CI after persistence."""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from analytics_reporter import send_weekly_report
from learning_engine import run_weekly_learning

STATUS_PATH = Path('reports/weekly-run.json')


def run():
    results = {}
    for name, action in [('performance_report', send_weekly_report), ('learning', run_weekly_learning)]:
        try:
            results[name] = bool(action())
        except Exception as exc:
            logging.error('Weekly %s failed (%s)', name, type(exc).__name__)
            results[name] = False
    result = dict(generated_at=datetime.now(timezone.utc).isoformat(),
                  success=all(results.values()), steps=results)
    STATUS_PATH.parent.mkdir(exist_ok=True)
    STATUS_PATH.write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    if '--check-status' in sys.argv:
        sys.exit(0 if json.loads(STATUS_PATH.read_text())['success'] else 1)
    print(json.dumps(run()))
