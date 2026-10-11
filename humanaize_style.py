"""Editorial adaptation of yapsgg/humanaize for factual video narration.

HumanAIze's prompt favors clear, conversational writing, active voice and
varied phrasing. Its generic essay advice is narrowed here to sourced market
scripts: no invented personal experience, emotion, motive or financial claim.
Source: https://github.com/yapsgg/humanaize (Apache-2.0).
"""

HUMANAIZE_NARRATION = """NARRATION STYLE (adapted from HumanAIze):
- Write like a thoughtful person explaining this specific event aloud to one viewer.
  Use active voice, plain words, short spoken sentences and natural transitions.
- Vary sentence length and openings. Let the verified event shape the rhythm;
  avoid canned hooks, repeated phrases, generic enthusiasm and formal essay prose.
- Where useful, make an abstract market mechanism concrete with a brief everyday
  analogy. An analogy illustrates a sourced fact; it must not add a new fact.
- Do not invent anecdotes, personal experiences, feelings, investor reactions,
  motives, quotes, causes, figures or certainty. Do not write as an eyewitness.
- Preserve dates, attribution, uncertainty and caveats from the supplied facts.
  Clarity and accuracy outrank style. Keep the requested word count and JSON schema.
"""
