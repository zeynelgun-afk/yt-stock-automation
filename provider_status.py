"""Static local transport contract. No auth access, status API or inference probe."""
import json
import os
from datetime import datetime, timezone

from config import OUTPUT_DIR
from llm_transport import MODEL, PROVIDER


def inspect_local():
    return dict(provider=PROVIDER, model=MODEL,
                checked_at=datetime.now(timezone.utc).isoformat(),
                status='not_live_verified', generation_tested=False, paid_fallback=False)


def main():
    result = inspect_local()
    (OUTPUT_DIR/'editorial_provider_status.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as summary:
            summary.write('\nLocal Hermes subscription configured; inference/auth not live verified. No paid fallback.\n')


if __name__ == '__main__': main()
