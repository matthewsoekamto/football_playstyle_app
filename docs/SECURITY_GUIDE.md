# SECURITY GUIDE

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Scope is honest about the project's actual size: this is a small, unauthenticated, read-only Streamlit analytics app. The point of this guide is to keep it that way safely, and to set the bar correctly for the features that *would* expand the attack surface.

---

## 1. Current Attack Surface (as of this snapshot)

- **No authentication, no user accounts, no PII.** The app reads one bundled, public-domain-adjacent statistics CSV and renders it. There is no user-submitted data path in `app.py` today beyond a free-text search box (`st.text_input`) that only ever flows into a `pandas` `.str.contains()` call — never into a SQL query, a shell command, or a template that gets executed.
- **No secrets exist in the codebase** — no API keys, tokens, or credentials anywhere in the inspected files. Keep it this way; see §4.

## 2. Input Validation

- `apply_search_filter`'s user-supplied `search_query` is passed to `pandas.Series.str.contains(..., na=False)` — this is safe (no regex injection risk in practice since it's matched against an in-memory column of names, not used to construct a query against an external system), but if this search is ever extended to build a raw SQL `LIKE` clause or shell command in the future, it must be parameterized, never string-concatenated.
- `st.selectbox`/`st.multiselect` values are constrained to a pre-computed list of valid options (`sorted(clustered_data["comp"].dropna().unique())`, etc.) — Streamlit widgets structurally prevent arbitrary user input here, which is the correct, safest pattern; do not replace these with free-text inputs without a specific reason.
- **Gap**: `load_app_data("data/players_data_light-2025_2026.csv")` performs no validation that the loaded CSV actually has the expected shape/columns before downstream code assumes `player`, `pos`, `min`, `90s`, etc. exist. A missing or unparseable CSV now produces a clear error message (via `data_loader.py`'s `try/except` on `pd.read_csv`), but a CSV with unexpected column names will still raise a raw `KeyError`/traceback. See `STYLE_GUIDE.md §9` and `TESTING_GUIDE.md §6` — this is a robustness issue today; it becomes a *security-relevant* issue the moment any future feature allows a user to supply or point to their own CSV (e.g. a file-upload feature), at which point strict schema/column validation before processing becomes mandatory, not optional.

## 3. Unsafe Operations

- No use of `eval`, `exec`, `pickle.load` on untrusted input, `os.system`, or raw SQL anywhere in the codebase. **This must remain true.** If model persistence is added (`ML_GUIDELINES.md §11`) via `joblib`/`pickle`, the loaded artifact must always be one the project itself produced and controls (e.g. committed to the repo or produced by a trusted CI job) — never a `pickle`/`joblib` file sourced from user upload or an untrusted URL, since deserializing untrusted pickles is arbitrary code execution.
- `pd.read_html` on user-supplied HTML must never be added to the live app without sanitization review.

## 4. Secrets Management

- None exist today; no `.env`, no API keys. If any are introduced (e.g. a future API-based data source), they must be loaded via environment variables (e.g. `os environ` or Streamlit's `st.secrets`), never hardcoded in `.py` files, and `.gitignore` must be updated to exclude any local secrets file before it's introduced — note the repo currently has **no `.gitignore` at all** (see `TASK_BACKLOG.md`), which should be added proactively, before it's needed, precisely to avoid an accidental first-time secret commit.

## 5. Configuration

- All configuration is currently hardcoded constants in source (`ARCHITECTURE.md §7`) — this is actually a *safer* default than premature environment-variable configuration for a project with no secrets and no per-environment behavior differences yet. Do not introduce configuration complexity (env vars, config files) purely for security-theater reasons; introduce it when a real per-environment or secret-bearing value exists.

## 6. File Handling

- The only file read is a bundled, repo-local CSV path, hardcoded as a string literal — not derived from user input, so there is no path-traversal risk today.
- **Forward-looking rule**: if a file-upload feature is ever added (e.g. "upload your own season CSV"), it must (a) validate file size before reading fully into memory, (b) validate the file extension and, ideally, sniff actual content rather than trusting the extension, (c) never use the user-supplied filename directly in a filesystem path (avoid path traversal via `../../` in a filename), and (d) run the same schema validation described in §2 before any processing.

## 7. Dependency Management

- `requirements.txt` pins **lower bounds only** (`streamlit>=1.28.0`, `pandas>=2.0.0`, `scikit-learn>=1.3.0`, `plotly>=5.18.0`) with no upper bounds and no lockfile. This is a supply-chain and reproducibility risk (a future transitive dependency update could silently change behavior or introduce a vulnerability) — recommended direction (tracked in `TASK_BACKLOG.md`, not applied here): adopt a lockfile (`pip-compile`/`poetry.lock`/`uv.lock`) that pins exact, hash-verified versions for deployment, while keeping the human-edited `requirements.txt` as loose bounds for development.
- Any new dependency added must be pinned the same way as the rest.
- No automated dependency vulnerability scanning (e.g. `pip-audit`, GitHub Dependabot) currently runs — recommended as a lightweight CI addition once CI exists at all (`TESTING_GUIDE.md`).

## 8. Logging

- No logging framework exists (`STYLE_GUIDE.md §8`); the only output is `print()` in `__main__` demo blocks. From a security standpoint: **never log full row contents or the entire DataFrame** if logging is introduced later — player statistics are not sensitive, but establishing a habit of dumping full data structures to logs is a bad pattern to carry forward into any future feature that *does* touch sensitive data (e.g. if user accounts are ever added).

## 9. Security Best Practices Summary Checklist

- [ ] No secrets in source control.
- [ ] No `eval`/`exec`/`os.system`/untrusted `pickle` anywhere.
- [ ] All user-facing inputs are either constrained widgets (`selectbox`/`multiselect`) or safely used (search box → `.str.contains`).
- [ ] Any future file-upload feature validates size, type, and schema before processing.
- [ ] Any future persisted model artifact is trusted/first-party only.
- [ ] Dependencies eventually get upper-bound pins / a lockfile before "Production Ready."
- [ ] Scraping (if ever revisited) stays manual, rate-limited, and out of the live request path.
