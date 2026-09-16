# Channel growth repair and measurement

User authorized implementation and release without further questions on 2026-09-16.

## Decision

Fix editorial eligibility and publication history before changing visual assets or increasing output. Prompt-only changes cannot enforce this; a full manual editorial workflow conflicts with unattended operation. Use deterministic admission rules, persistent YouTube event tags, and an automated read-only experiment report.

## Publication rules

- Read authenticated, paginated upload history. History failure stops production; an empty valid history is distinct from failure.
- Fingerprint each sourced event using its issuer, event type, source date and actor/source identity. Ignore changing market prices and generated titles. Persist event and issuer tags on upload across Shorts and long videos.
- Block a matching event within 30 days and any tagged company repeat within 48 hours across formats (a conservative editorial cooldown, even for a new event). Use a five-day legacy title/name fallback for untagged uploads, including company names in source headlines. No fallback may restore excluded candidates.
- Admit only dated congressional disclosures, dated insider transactions, reported earnings, dated analyst news, or movers with recent source-linked news. Mention counts, market-wide gauges and generic recaps alone are not eligible during this experiment. A missing candidate produces an explicit skip before generation.
- Apply the existing minimum score before trend/learning bonuses, for both formats. Add an editorial relevance field grounded in source facts. Remove conflicting franchise instructions and unrelated market context from single-company script inputs.
- Tag new Shorts with the experiment ID. Save decisions and source facts as workflow artifacts, without credentials.

## Measurement

Daily report, no LLM or paid generation: compare first ten experiment Shorts with last ten pre-experiment Shorts. Use the first three complete Pacific calendar days after publication, excluding the partial publication day; this is not an exact first-72-hour report and DST can change its elapsed length. Wait at least two further days for Analytics; label pending/missing metrics and do not infer swipe rate or CTR. Keep counts and actual sample windows visible. Persist JSON and Markdown in the repository. Do not declare success before ten eligible experimental uploads and enough engaged views.

## Provider failure

The latest production run failed with an OpenRouter monthly key limit. Do not increase spend or swap credentials/providers to evade it. Make account failures terminal for the run and omit provider response bodies from logs. Verify selection and reporting without generation charges; report publication as blocked until the configured account works.

## Validation and release

Regression tests: restored duplicates, source-headline legacy matches, event stability, pagination and history outage, stale/weak candidates, pipeline early skip, provider limit terminal behavior, report windows and pending data. Run existing full suite, live read-only selection, live report, then push and verify CI plus the report workflow. No new video is required to prove the gate; actual publication remains separately reported.
