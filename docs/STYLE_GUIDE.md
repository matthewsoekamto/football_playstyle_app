# STYLE GUIDE
### Python coding standards for this repository

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Applies to every `.py` file in the repo, including future test files.

---

## 1. General Philosophy

PEP8 as the baseline, SOLID/DRY/KISS/YAGNI as the judgment layer on top. The existing modules (`features.py`, `charts.py`) are good reference examples: short, single-purpose functions, no god-objects, no premature abstraction. New code should match this bar, not exceed it with speculative flexibility (YAGNI).

## 2. Naming

- **Modules**: lowercase, single word or `snake_case` (`data_loader.py`, `model_engine.py`) — matches current convention. Do not introduce `CamelCase` module names.
- **Functions**: `snake_case`, verb-first (`load_and_clean_data`, `build_scatter_chart`, `add_position_percentiles`). A function named `data` or `stats` (noun-only) is a naming smell — rename to describe the action.
- **Private/internal helpers**: prefix with `_` exactly as already done (`_add_per90_rates`, `_available_features`, `_archetype_matrix`, `_assign_labels_from_archetypes`). Any function not part of a module's public contract (i.e. not imported elsewhere) must get the `_` prefix.
- **Constants**: `UPPER_SNAKE_CASE` at module level, exactly as done today (`FRIENDLY_NAMES`, `OUTFIELD_FEATURES`, `POSITION_COMPARE_STATS`, `EXPLORER_GK_FEATURES`). Never define a "constant" as a re-computed value inside a function body if it doesn't depend on function arguments.
- **DataFrame column names**: lowercase with underscores, matching the normalization already performed in `data_loader.load_and_clean_data` (`df.columns.str.strip().str.lower().str.replace(" ", "_").str.replace("-", "_")`). Any new derived column must follow this convention (e.g. `xg_p90`, not `xG_Per90`).
- **Booleans/masks**: name for what they select, not what they are (`dup_mask`, `position_mask` — already good practice in `app.py` / `features.py`). Continue this.

## 3. Imports

- Standard library, then third-party, then local project imports — each group separated by a blank line, alphabetized within a group. `app.py` already does this correctly (`unicodedata` / `pandas`+`streamlit` / local `charts`, `features`, `model_engine`).
- No wildcard imports (`from x import *`) anywhere, ever.
- No import-time side effects beyond what Streamlit itself requires. Note: `app.py` currently executes top-level Streamlit calls (`st.set_page_config`, data loading, rendering) at module scope rather than inside a `main()` guarded by `if __name__ == "__main__":`. This is idiomatic *for Streamlit specifically* (Streamlit re-executes the script file directly) and should **not** be "fixed" by wrapping it in `main()` — that would break the app. `data_loader.py` and `model_engine.py`, by contrast, correctly guard their demo code with `if __name__ == "__main__":`; any new standalone script must follow that pattern.

## 4. Functions

- One responsibility per function. If you need "and" to describe what a function does, split it. (`_add_per90_rates` is a good example of the right size.)
- Keep Streamlit rendering functions (`render_sidebar_filters`, `render_playstyle_explorer`, `render_h2h_section` in `app.py`) separate from data/compute logic — this separation already exists and must be preserved. A `render_*` function should not contain `groupby`/`merge`/statistical computation; that belongs in `features.py` or `model_engine.py`.
- Default to pure functions (no hidden global state, no mutation of arguments unless explicitly documented) — `charts.py` is entirely pure today; keep it that way.
- Prefer explicit keyword arguments for functions with more than 2 parameters, matching `filter_dataframe(df, leagues=None, positions=None, squads=None, playstyles=None, search_query=None)`.

## 5. Classes

- The codebase currently has **zero classes** — everything is functions + module-level constants + DataFrames. This is an intentional, appropriate style for a data pipeline of this size. Do not introduce classes (e.g. a `PlayerRepository` or `ClusteringModel` class) without a documented reason in `DECISIONS.md`; a class introduced "for organization" without new state to encapsulate is a YAGNI violation here.
- If a future feature genuinely needs encapsulated state (e.g. a model object that persists across calls — see `TASK_BACKLOG.md` ML-03 on model persistence), a class or a small `dataclass` is appropriate then, not before.

## 6. Type Hints

**Currently absent from the entire codebase.** This is a known gap (see `PROJECT_IMPROVEMENT_REPORT.md`), not the target state. Going forward:

- All **new** functions must have type hints on parameters and return values.
- Use `pandas.DataFrame`, `pandas.Series`, `list[str]`, `str | None` (PEP 604 union syntax, since `requirements.txt` implies Python 3.10+ per `README.md`).
- Do not do a mass retrofit of type hints onto existing functions as a standalone change — that's a repo-wide diff with no functional benefit and high review cost. Add hints opportunistically whenever a function is touched for another reason (`AI_DEVELOPER_RULEBOOK.md §Incremental Refactors`).

Example of the target style for new code:
```python
def compute_playstyle_share(df: pd.DataFrame, playstyle_col: str = "Playstyle") -> pd.Series:
    """Return the fraction of rows in each playstyle bucket."""
    return df[playstyle_col].value_counts(normalize=True)
```

## 7. Docstrings

- Every public (non-`_`-prefixed) function needs a one-to-three-line docstring stating *what it returns and why*, not a restatement of its name. `app.add_unique_player_labels` is the gold-standard example already in the repo — it explains the *why* (mid-season transfers) not just the *what*.
- Private helper functions may skip the docstring **only if the function body is fully self-explanatory in under 5 lines** (e.g. `_available_features`); anything with a non-obvious algorithm (`_assign_labels_from_archetypes`) needs one even though it's private.
- Module-level docstrings are optional for now given the small module count, but any module whose purpose isn't obvious from its name+first-function should get one.

## 8. Logging

**Currently the codebase uses `print()` exclusively**, and only inside `if __name__ == "__main__":` demo blocks in `data_loader.py` and `model_engine.py`. Rules going forward:

- Never use `print()` inside code that runs as part of the Streamlit app itself (`app.py`, or any function called from it) — use `st.error` / `st.warning` / `st.info` for user-facing messages (already the pattern in `app.py`, e.g. `st.info("No playstyle profiles available for the current filters.")`).
- `print()` remains acceptable *only* in `__main__` demo/debug blocks, matching current usage.
- If/when a real logging need arises (e.g. logging cache misses, data quality warnings), introduce Python's standard `logging` module with a module-level `logger = logging.getLogger(__name__)` — do not introduce a third-party logging library for a project this size.

## 9. Error Handling & Exceptions

- Never let a raw exception reach the Streamlit UI as an unhandled traceback. Currently, `pd.read_csv` in `data_loader.load_and_clean_data` has **no error handling** — a missing/malformed CSV will crash the app with a full traceback visible to the end user. Any change touching this function must wrap the read in a `try/except` and surface a clear `st.error(...)` message (see `TESTING_GUIDE.md` for the corresponding test case).
- Catch the narrowest exception type you can reasonably anticipate (`FileNotFoundError`, `pd.errors.ParserError`, `KeyError` for missing required columns) rather than bare `except Exception`. The `__main__` blocks in `data_loader.py`/`model_engine.py` currently use `except Exception as e: print(f"ERROR: {e}")` — acceptable for a CLI debug entrypoint, not acceptable inside the app itself.
- Never swallow an exception silently (`except: pass`). None currently exist in the codebase — keep it that way.

## 10. Comments

- Comment *why*, not *what*. Good existing example: `# FBref uses multi-level headers — flatten them` in `fetch_possession_stats.py`. Bad example to avoid: a comment that just restates the line below it in English.
- Delete commented-out code before merging; never leave it "just in case." (`fetch_possession_stats.py` currently contains one line of genuinely dead code — see `PROJECT_IMPROVEMENT_REPORT.md` — that should be removed the next time that file is touched, per `AI_DEVELOPER_RULEBOOK.md`'s incremental-fix rule, not as an unrelated drive-by edit.)

## 11. Formatting

- PEP8, 4-space indentation, no tabs — already consistent throughout.
- Line length: target ~100 columns (the codebase's existing multi-line function calls with trailing commas, e.g. in `app.py`'s `st.selectbox` calls, already imply this convention). Do not enforce a hard 79-column PEP8 line length retroactively.
- Trailing commas on multi-line collections/calls, matching existing style.
- If a formatter is adopted, prefer `black` with default settings and `isort` for import ordering — but this must be introduced as an explicit, documented change (a repo-wide reformat is a large diff and must not be bundled with a functional change).

## 12. SOLID / DRY / KISS / YAGNI in this codebase, concretely

- **DRY violation to fix opportunistically**: `features.filter_dataframe` accepts a `search_query` parameter that is **never used** by its body and is never passed by its only caller (`app.py` calls `apply_search_filter` separately). This is dead/misleading surface area — flagged in `TASK_BACKLOG.md` (STYLE-01), not fixed silently by this documentation pass.
- **KISS respected**: `charts.py` takes plain arguments and returns a `Figure` — no config objects, no inheritance. Keep new chart functions this simple.
- **YAGNI respected**: no ORM, no plugin system, no abstract base classes for a 5-module app. Do not add any of these without a `DECISIONS.md` entry justifying the need.

## 13. Dependency Injection & Configuration

- Functions take the data they operate on as parameters (`build_scatter_chart(plot_df, x_axis, y_axis, ...)`) rather than reaching into global state — this **is** the project's dependency-injection style, and it's correct for this scale. Do not introduce a DI framework.
- Configuration is currently hardcoded (see `ARCHITECTURE.md §7`). New configurable values should be added as module-level constants first (matching `OUTFIELD_FEATURES` style); only promote to an actual config file/env-var system when a second deployment target or a second dataset genuinely requires it (see `TASK_BACKLOG.md`).

## 14. Constants

- Every "magic number" introduced going forward must be a named constant with a comment explaining its origin if it's not self-evident (e.g. `MIN_MINUTES_THRESHOLD = 270  # three full 90-minute matches`). Existing magic numbers (`270`, `5`, `2`, `42`) are grandfathered but should be extracted the next time their owning function is meaningfully touched.

## 15. Testing (see `TESTING_GUIDE.md` for full detail)

- New logic must be written in a way that's testable without Streamlit running — this is already true of `data_loader.py`, `model_engine.py`, `features.py`, and `charts.py` (none import `streamlit` except `data_loader.py`/`model_engine.py`'s `@st.cache_data` decorator, which is safely a no-op-compatible decorator outside a Streamlit runtime). Preserve this: business logic must never require `streamlit.runtime` to execute.

## 16. Documentation

- Any change to a function's inputs, outputs, or behavior must update its docstring in the same commit.
- Any change to module responsibilities must update `ARCHITECTURE.md` in the same commit (`PROJECT_CONSTITUTION.md §Definition of Done`).

## 17. Refactoring

- Refactor in the smallest correct slice. Never combine a refactor with a feature addition in the same diff — this is a hard rule from `PROJECT_CONSTITUTION.md §12`, restated here because it's the single most common way AI agents produce unreviewable diffs.

## 18. Forbidden Patterns

- ❌ `except Exception: pass` (silent failure).
- ❌ Wildcard imports.
- ❌ New global mutable state (module-level lists/dicts that get mutated at runtime rather than treated as constants).
- ❌ Business logic (data cleaning, clustering, statistics) inside `app.py`'s `render_*` functions.
- ❌ Hardcoding a second copy of any value already defined in `FRIENDLY_NAMES`, `POSITION_COMPARE_STATS`, `OUTFIELD_FEATURES`/`GK_FEATURES`, or `OUTFIELD_ARCHETYPES`/`GK_ARCHETYPES` — import and reuse the existing constant.
- ❌ `print()` inside app-rendering code paths.
- ❌ Introducing a new third-party dependency without adding it to `requirements.txt` in the same change.
- ❌ Committing commented-out code or leftover debug prints.
- ❌ Dead/no-op code such as the unused lambda-conditional line currently in `fetch_possession_stats.py` (`comments = soup.find_all(string=lambda text: isinstance(text, type(soup.find(string=True).__class__) or True) if False else True)`) — this evaluates and is immediately discarded by the next line; new code must never ship a similar leftover.
