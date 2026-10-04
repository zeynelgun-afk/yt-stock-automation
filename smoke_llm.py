#!/usr/bin/env python3
"""Operator-only REAL subscription smoke. Never mock inference in this script.

Synthetic supplied facts only; exercises both public generation entry points.
No publication or external data access. Script correction loop is bounded at 3;
ReplyWriter makes 1 request, so a successful smoke uses 2-4 real contexts.
"""
import json
import os
from pathlib import Path

from script_generator import ScriptGenerator
from comment_responder import ReplyWriter, parse_reply
from editorial_policy import validate_editorial_script

FACTS = '''SYNTHETIC TEST FACTS, not a real company or market event:
Example Widget Corporation (ticker XWTEST) reported quarterly revenue of
$12 million versus $10 million in the same quarter last year. Management said
higher unit sales contributed to revenue growth. The supplied facts contain
no profit figures, share-price movement, valuation or outlook. Explain revenue
growth and explicitly distinguish it from profitability. Do not invent facts.'''


def main():
    if os.getenv('YT_OFFLINE_TESTS') == '1':
        raise RuntimeError('Smoke requires real inference; forbidden in offline suite')
    # Suppress optional disk-derived learnings: this smoke uses supplied facts only.
    import script_generator
    script_generator._learnings = lambda: {}
    script = ScriptGenerator().generate_shorts_script('Example Widget Corporation revenue', FACTS)
    errors = validate_editorial_script(script,dict(ticker='XWTEST',franchise='earnings_shock'))
    if errors: raise RuntimeError('Smoke script failed editorial validation')
    reply = ReplyWriter().draft('Does revenue growth also mean profits increased?',
        dict(title=script['title'],description=FACTS), [])
    if not reply or parse_reply(json.dumps(dict(action='reply',language='en',text=reply))) != reply:
        raise RuntimeError('Smoke reply failed existing reply validation')
    output = Path(__file__).resolve().parent/'output'; output.mkdir(exist_ok=True)
    report = dict(provider='openai-codex',model='gpt-6-astra',synthetic_facts=True,
                  real_inference=True,script=script,reply=reply,published=False)
    (output/'llm_smoke.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Real subscription script and reply smoke passed; nothing published.')


if __name__ == '__main__': main()
