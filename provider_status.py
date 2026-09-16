"""Read-only OpenRouter key-quota probe; never generates, changes limits or keys."""
import json
import math
import os
from datetime import datetime, timezone

import requests

from config import OPENROUTER_API_KEY, OUTPUT_DIR


def inspect_openrouter():
    result = {'provider': 'openrouter', 'checked_at': datetime.now(timezone.utc).isoformat(),
              'status': 'unknown', 'generation_tested': False}
    if not OPENROUTER_API_KEY:
        return {**result, 'status': 'not_configured'}
    try:
        response = requests.get('https://openrouter.ai/api/v1/key',
                                headers={'Authorization': f'Bearer {OPENROUTER_API_KEY}'}, timeout=20)
        if response.status_code != 200:
            return {**result, 'status': 'unavailable', 'http_status': response.status_code}
        data = response.json()['data']
        remaining = data.get('limit_remaining')
        if isinstance(remaining, (int, float)) and math.isfinite(remaining):
            result['status'] = 'quota_exhausted' if remaining <= 0 else 'quota_available'
        elif remaining is None and data.get('limit') is None:
            result['status'] = 'no_key_limit'
        result['limit_reset'] = data.get('limit_reset')
    except Exception as exc:
        result['error_type'] = type(exc).__name__
    return result


def main():
    result = inspect_openrouter()
    (OUTPUT_DIR / 'editorial_provider_status.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary:
            summary.write(f"\nOpenRouter read-only quota check: **{result['status']}**. "
                          'No generation or publication was attempted.\n')
    # A successful inspection can reveal a blocked account. The artifact and
    # summary describe readiness; this diagnostic exit status is not a publish.


if __name__ == '__main__':
    main()
