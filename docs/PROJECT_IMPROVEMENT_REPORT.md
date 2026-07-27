# PROJECT IMPROVEMENT REPORT

Authority: subordinate to `PROJECT_CONSTITUTION.md`. This is a point-in-time engineering review of the repository as inspected (all 5 core modules, `README.md`, `requirements.txt`, and the actual dataset). Scores are out of 10 and are meant to be defensible by specific reference to code, not vibes.

---

## Scorecard

| Dimension | Score /10 | One-line justification |
|---|---|---|
| Architecture | 8 | Clean 5-module separation with correct dependency direction; no test/config layer yet. |
| ML | 6 | Sound normalization and reproducibility (seeded), but zero evaluation metrics and a statistically fragile archetype-matching scaler. |
| UI | 8 | Coherent, product-quality Streamlit UI with good empty-state handling; no session state needed yet, appropriately. |
| Performance | 8 | Correct three-layer caching for the only expensive operation; nothing at current scale is actually slow. |
| Code Quality | 6 | Readable, well-named, mostly single-purpose functions; zero type hints, minimal docstrings, one unused parameter. |
| Maintainability | 6 | Small and legible today; no tests to protect against regressions as it grows; one architecturally orphaned file. |
| Scalability | 5 | Hardcoded single-file, single-season design; caching not keyed to data content. |
| Security | 7 | Small, mostly safe attack surface; no secrets; gaps are all in the "not yet needed but will be" category. |
| Documentation | 4 (pre-this-effort) → this `/docs` set directly addresses this | No `/docs` existed before this deliverable; `README.md` alone was accurate but shallow. |
| Professionalism | 7 | Thoughtful product framing (chart titles, warnings, empty states) exceeds the "quick script" bar. |
| Portfolio Readiness | 6 | Strong demo material; missing tests/CI is the single biggest gap for a portfolio reviewer with ML/SWE background. |
| **Overall** | **6.5 / 10** | A genuinely well-built small analytics app held back almost entirely by absent tests/CI and a few fragile ML details — not by fundamental design flaws. |

---

## Detailed Weaknesses

### Architecture (8/10)
**Strength:** The `data_loader → model_engine → features/charts → app` layering is correct and consistently respected — there is no instance of, e.g., clustering logic leaking into `app.py`, or UI code leaking into `model_engine.py`.
**Weakness:** No `tests/` or `config/` layer exists. A standalone scraper (`fetch_possession_stats.py`, since deleted in v1.0) sat outside the module graph with no formal status (documented at the time via `DECISIONS.md` ADR-005).

### ML (6/10)
**Strength:** Per-90 normalization, seeded KMeans (`random_state=42`), sensible outfield/GK model split, human-authored archetype labeling that requires no labeled training data.
**Weakness:** The archetype-matching `StandardScaler` in `_assign_labels_from_archetypes` is fit on only 5 (or 2) centroid points — a genuinely thin statistical basis (`DECISIONS.md` ADR-002). Zero evaluation metrics (no silhouette score, no Davies-Bouldin index) exist anywhere, meaning cluster quality has never been objectively measured, only eyeballed. `fillna(0)` before percentile ranking produces meaningless-but-present percentile columns for position-irrelevant stats.

### UI (8/10)
**Strength:** Every empty/insufficient-data state is handled with a specific `st.info`/`st.warning` message, not silently blank or crashing. Chart titles and section headers are consistently product-facing English, not engineering jargon.
**Weakness:** No loading state beyond the single top-level spinner; a future slow operation (e.g. live filtering on a much larger dataset) has no established pattern for a secondary loading indicator.

### Performance (8/10)
**Strength:** The one genuinely expensive operation (CSV load + dual KMeans fit) is correctly cached three layers deep.
**Weakness:** Cache keys don't incorporate the CSV's content/mtime, so replacing the data file silently serves stale results until process restart — an easy-to-miss operational gotcha (`PERFORMANCE_GUIDE.md §4`).

### Code Quality (6/10)
**Strength:** Consistent naming conventions, short single-purpose functions, no obvious code smells beyond the two specific issues below.
**Weakness:** Zero type hints across the entire codebase. `features.filter_dataframe` has an unused `search_query` parameter — a real, verifiable dead-parameter defect, not a style nitpick.

### Maintainability (6/10)
**Strength:** Small enough today that any single engineer (human or AI) can hold the whole system in working memory.
**Weakness:** Zero automated tests means every future change is a manual-verification-only change — the single largest maintainability risk as the project grows past its current size.

### Scalability (5/10)
**Strength:** Handles current data volume (2,839 raw / 2,183 filtered rows) with no measurable latency.
**Weakness:** Filename, minutes-threshold, cluster counts, and archetype definitions are all hardcoded constants with no configuration layer; there is no multi-season data model; the project's stated future goals (multi-season, possession stats) both require real architectural additions, not just parameter tweaks.

### Security (7/10)
**Strength:** No secrets, no auth surface, no unsafe deserialization, no SQL, minimal and safe user input handling.
**Weakness:** No CSV schema validation before processing (a real robustness/security gap the moment file upload is ever considered); dependencies are pinned with lower bounds only, no lockfile.

### Documentation (pre-existing: 4/10 — addressed by this deliverable)
**Strength (pre-existing):** `README.md` was accurate, concise, and correctly described setup/run/deploy steps.
**Weakness (pre-existing):** No architecture doc, no ML rationale doc, no decision log, no AI-agent operating rules existed before this `/docs` set — meaning every non-trivial "why" behind the code (e.g. why two KMeans models, why `fillna(0)`, why `Min >= 270`) lived only in the original author's head.

### Professionalism (7/10)
**Strength:** The attention to UX details (warnings when comparing across positions, duplicate-name disambiguation, rounded metric deltas) reflects product thinking beyond a typical "notebook-to-Streamlit" port.
**Weakness:** No CI badge, no test badge, no contribution guide — the repository doesn't yet *look* production-grade at a glance, even though the code inside it is reasonably solid.

### Portfolio Readiness (6/10)
**Strength:** A working, deployed-ready, visually coherent ML+data app is inherently strong portfolio material.
**Weakness:** A technical reviewer (the exact audience this project targets per `PROJECT_SPEC.md §3`) will immediately notice the absence of tests and will reasonably discount the ML rigor score until the archetype-scaling fragility and missing evaluation metrics are addressed.

---

## Recommendations Ranked by ROI

ROI = impact on the scorecard above ÷ estimated effort (from `TASK_BACKLOG.md`).

| Rank | Task ID | Why it's high ROI |
|---|---|---|
| 1 | `SEC-01` (graceful CSV load failure) | ~1 hour of effort eliminates the single most visible failure mode (a raw traceback on a missing file) a portfolio reviewer or real user could hit immediately. |
| 2 | `TEST-01` (determinism test + initial suite) | A few hours of effort directly moves both "Maintainability" and "Portfolio Readiness" scores, and is a prerequisite for safely doing everything below it. |
| 3 | `STYLE-01` (remove unused `search_query` param) | Trivial effort, removes a real, citable code-quality defect. |
| 4 | `STYLE-02` (remove dead code in scraper) | Trivial effort, same category as above. |
| 5 | `ML-01` (fix archetype-matching scaler) | Medium effort, but directly addresses the single most substantive ML critique a technically sophisticated reviewer would raise. |
| 6 | `ML-04` (add silhouette/Davies-Bouldin metrics) | Low effort, high signal — turns "we assume the clusters are good" into "here is the number that shows it," which matters disproportionately for portfolio credibility. |
| 7 | `DEP-01` (`.gitignore` + dependency pinning) | Low effort, removes latent supply-chain and accidental-secret-commit risk before it's ever tested by an incident. |
| 8 | `ML-02` (scope percentiles to relevant stats) | Medium effort, fixes a real (if currently harmless) data-correctness issue. |
| 9 | `CI-01` (basic CI) | Low-medium effort once `TEST-01` exists; makes every subsequent change cheaper to trust. |
| 10 | `DATA-01` (possession stats integration) | Highest absolute impact on the product, but also the highest effort and the most risk (re-tuning archetypes) — correctly sequenced after the ML fragility fix and the test suite exist. |
| 11 | `ML-03` (model persistence) | Real value, but lower urgency than the above — current recompute cost is negligible at this data scale. |
| 12 | `FUT-01`–`FUT-04` | Legitimate future value, but explicitly out of near-term ROI given current scope (`PROJECT_SPEC.md §17` Feature Complete definition is already met without them). |

## Summary Judgment

This is a **well-architected small project with an incomplete engineering-maturity layer around it**, not a poorly-designed one. The five core modules demonstrate real judgment (correct separation of concerns, honest handling of the outfield/GK asymmetry, thoughtful empty-state UX). The gap between a 6.5/10 and an 8.5+/10 overall score is concentrated almost entirely in three fixable places: **no tests, one statistically fragile scaling choice, and zero ML evaluation metrics.** None of these require a rewrite — all are additive, scoped, `TASK_BACKLOG.md`-tracked changes.
