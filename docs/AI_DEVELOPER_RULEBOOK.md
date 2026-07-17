# AI DEVELOPER RULEBOOK
### For Claude Code, Cursor, Continue, Cline, GitHub Copilot, GPT-based agents, and any future AI coding agent

Authority: subordinate to `PROJECT_CONSTITUTION.md`, which this document operationalizes. **Treat the AI agent as a capable, fast, but context-blind junior engineer** — these rules exist to compensate for the specific ways that persona fails, not as generic caution.

---

## 1. Before Touching Anything

1. **Always read `ARCHITECTURE.md` first**, then read every file you intend to modify in full — not a snippet, not a search-result excerpt. This codebase is small (5 core modules); there is no excuse for a partial read.
2. **Identify which module owns the responsibility you're about to change**, using the table in `ARCHITECTURE.md §1`. If your change would mean adding clustering logic to `app.py` or UI rendering to `model_engine.py`, stop — you're about to violate the module boundary; the code belongs in a different file.
3. **Check `DECISIONS.md` for an existing ADR** covering the area you're about to touch before assuming something is a bug. Several things that look like bugs at a glance are documented, deliberate tradeoffs (e.g. the `fillna(0)`-before-percentile behavior in ADR-007, the disconnected `fetch_possession_stats.py` in ADR-005). Changing a documented decision requires a new ADR, not a silent fix.
4. **Check `TASK_BACKLOG.md`** — if the thing you noticed is already tracked there, don't fix it as an unrelated drive-by edit inside a different task; do it as its own change, referencing the backlog item.

## 2. Rules for Every Change

- **Never modify unrelated code.** If you're asked to fix the H2H comparison and you notice the unused `search_query` parameter in `filter_dataframe` (`STYLE_GUIDE.md §12`, `TASK_BACKLOG.md` STYLE-01), do not fix it in the same diff — mention it, but leave it alone unless asked.
- **Never introduce duplicate logic.** Before writing a new function, check whether `features.py`, `charts.py`, or `model_engine.py` already has something close to what you need. Example: friendly stat names already live in exactly one place (`FRIENDLY_NAMES`) — never hardcode a second display-name mapping anywhere.
- **Prefer incremental refactors.** A refactor and a feature addition must never share a diff (`PROJECT_CONSTITUTION.md §12`). If a feature requires a refactor first, do the refactor as its own reviewable change, confirm it still passes existing behavior, then add the feature.
- **Preserve backwards compatibility** of function signatures used across module boundaries (e.g. `get_clustered_data(filepath)`, `filter_dataframe(df, leagues=None, ...)`) unless the task is explicitly to change that contract. If you must change a signature, update every call site in the same change and search the whole repo for other callers first.
- **Explain your reasoning before large edits.** For any change touching more than one file, or touching `model_engine.py`'s clustering logic at all, state in plain language: what you're changing, why, and what you checked to confirm it's safe (e.g. "I re-read `ML_GUIDELINES.md §8` before changing `n_clusters`").
- **Never invent APIs.** Every `pandas`/`streamlit`/`plotly`/`scikit-learn` call you write must be one you can verify exists (via the installed version implied by `requirements.txt`, or by checking actual usage elsewhere in the repo). Do not guess a plausible-sounding method name.
- **Never remove functionality unless explicitly requested.** This includes UI sections, filters, warning messages (e.g. the GK-vs-outfield comparison warning in `render_h2h_section`), and defensive guards (e.g. the `if gk_features and not df_gk.empty:` check in `group_players`).
- **Respect architecture, naming, and module boundaries** as defined in `ARCHITECTURE.md` and `STYLE_GUIDE.md`. When genuinely unsure which module something belongs in, default to the most conservative option (extend an existing module) rather than creating a new one.
- **Follow `STYLE_GUIDE.md`, `ML_GUIDELINES.md`, and `STREAMLIT_GUIDELINES.md`** for any code in their respective domains — these are not optional style suggestions, they are the standard this repo is held to.
- **Always update documentation in the same change.** A change to `model_engine.py`'s feature lists updates `ARCHITECTURE.md §4` and possibly `ML_GUIDELINES.md`. A new UI section updates `ARCHITECTURE.md §5` and possibly `STREAMLIT_GUIDELINES.md`. A new dependency updates `requirements.txt` and possibly `SECURITY_GUIDE.md §7`.
- **Always consider performance** per `PERFORMANCE_GUIDE.md` — specifically: does this new computation need `@st.cache_data`? Does it introduce a Python-level loop where a vectorized pandas/numpy operation would do?
- **Always consider security** per `SECURITY_GUIDE.md` — specifically: does this touch user input, file I/O, or a new dependency?
- **Always consider testing** per `TESTING_GUIDE.md` — new logic needs new tests; a bug fix needs a regression test that fails before the fix and passes after.
- **Always explain changes** in a clear summary: what changed, why, what was verified, what (if anything) was deliberately left alone.

## 3. Specific Known Traps in This Codebase

These are real, verified details an AI agent is likely to get wrong if it doesn't read carefully:

- **`get_cluster_profiles` takes `playstyle_col="playstyle_cluster"` by default**, but `app.py` calls it with `playstyle_col="Playstyle"` (the renamed column from `load_app_data`). Do not "simplify" by removing the parameter or assuming the default is always correct — the column name genuinely differs between `model_engine.py`'s internal representation and `app.py`'s renamed one.
- **`primary_position` derivation happens in two places**: once in `data_loader.load_and_clean_data` (the normal path) and again, defensively, inside `model_engine.group_players` (`if "primary_position" not in df.columns: ...`). This is intentional defensive redundancy for when `group_players` is called on data that skipped `load_and_clean_data` — do not remove either copy without checking both call paths.
- **`OUTFIELD_FEATURES`/`GK_FEATURES` in `model_engine.py` and `EXPLORER_OUTFIELD_FEATURES`/`EXPLORER_GK_FEATURES` in `features.py` are two separate constant lists** with overlapping but not necessarily identical purposes (clustering input features vs. explorer-radar display features). They currently contain the same values, but do not assume they must always be identical, and do not merge them into one shared constant without checking both usages — clustering features and display features are allowed to diverge for good reason (e.g. wanting to *display* a stat on a radar without including it in the *distance metric*).
- **`int_p90` is computed twice** (once via `OUTFIELD_RATE_STATS`, once via `GK_RATE_STATS`, both include `"int"`) inside `data_loader._add_per90_rates`. This is harmless (idempotent recomputation of the same column) but is not a bug to "fix" by removing one list's `"int"` entry — doing so could break the assumption that each rate-stat list is independently complete for its consumer.
- **`fetch_possession_stats.py` is not dead code to delete** — it is a deliberately disconnected, manually-run utility (`DECISIONS.md` ADR-005). Do not "clean up" the repo by removing it.
- **Duplicate player names are real and expected** (152 in the current dataset) — do not "fix" `app.add_unique_player_labels` by assuming duplicates indicate a data quality bug; they represent genuine mid-season transfers.

## 4. What "Small, Correct Diff" Means Here

- A single bug fix touches the owning module and, if needed, its direct caller — not every file that could theoretically be affected.
- A new chart touches `charts.py` (the builder function) and `app.py` (the one `st.plotly_chart` call site) — not `features.py`, unless the chart genuinely needs a new derived stat that doesn't exist yet, in which case that addition goes in `features.py` as its own clearly-justified piece of the diff.
- A new filter dimension touches `features.filter_dataframe`, `app.render_sidebar_filters`, and the `filter_dataframe(...)` call site in `app.py` — a complete, minimal set, not a broader refactor of the filtering system.

## 5. When to Stop and Ask Instead of Guessing

- The task requires changing `random_state`, `n_clusters`, or the `Min >= 270` threshold — these are product/ML decisions (`DECISIONS.md` ADR-003/004), not pure engineering ones.
- The task requires adding a new third-party dependency for something a already-installed library (`pandas`, `numpy`, `scikit-learn`, `plotly`, `streamlit`) can already do.
- The task is ambiguous about which module should own new logic.
- The task would require deleting or fundamentally restructuring a documented decision without being explicitly told to revisit that decision.

## 6. After the Change

- Re-read the diff as if you were the reviewer, not the author: does every line answer "why is this here," not just "does this run"?
- Confirm `streamlit run app.py` would start cleanly and every existing section still renders (mentally trace: sidebar → table → explorer → scatter → H2H) — you cannot literally run it in all environments, so state clearly what you verified and how, and flag anything you could not verify.
- Summarize the change plainly enough that a human reviewer with no additional context could approve or reject it in under a minute.
