# STREAMLIT GUIDELINES
### UI handbook for the Football Playstyle App

Authority: subordinate to `PROJECT_CONSTITUTION.md`. Governs `app.py` and any future UI code.

---

## 1. Layout

- `st.set_page_config(page_title="Football Playstyle App", layout="wide")` is set once, at the top of `app.py`, before any other Streamlit call. Any new page (if the app ever becomes multi-page) must set this exactly once, at the top of its entrypoint.
- Wide layout is a deliberate choice given the chart-heavy content (radar charts, scatter plots side by side). Do not switch to `layout="centered"` without a product reason.
- Section ordering on the page follows a deliberate narrative: filters → search → table → Playstyle Explorer → scatter plot → head-to-head. New sections should be inserted where they fit this narrative (broad → specific), not appended to the bottom by default.

## 2. Spacing

- `st.divider()` is used consistently between major sections (already correctly placed between the table, the Playstyle Explorer, the scatter plot, and the head-to-head section). Every new top-level section must be preceded by a `st.divider()`.
- `st.subheader()` for section titles, `st.markdown("#### ...")` for sub-emphasis within a section (as in `render_h2h_section`'s player-vs-player header) — keep this two-level hierarchy; don't introduce `st.header()` (reserved, implicitly, for the page title via `st.title()`) inside sections.

## 3. Navigation

- Single-page app, no `st.sidebar` navigation beyond filters, no `st.tabs`/`st.pages` currently. This matches the current Feature Complete scope (`PROJECT_CONSTITUTION.md §17`). If the app grows to warrant multi-page navigation (e.g. a dedicated "Player Profile" page), that is a `DECISIONS.md`-worthy architectural change, not an incremental addition.
- A **dataset selector** (`st.sidebar.radio("Dataset", [v2, v1])`, v2 default) is a *filter*, not navigation — it selects which dataset/version to render, so it stays compatible with the single-page design (see `DECISIONS.md` ADR-012). It lives in the sidebar above the version-specific filters; the non-selected version's filters and sections are never rendered (guarded by `st.stop()`).

## 4. Component Hierarchy

- **Sidebar**: filters only (`render_sidebar_filters`) — league, position, squad, playstyle multiselects. Never put primary content controls (like the H2H player selectors) in the sidebar; they belong inline with the section they control, as currently implemented.
- **Main body**: search → table → explorer → scatter → H2H, each owned by a single `render_*` function (or inline script body for the simpler sections). Every new UI section should be its own `render_*` function taking the already-filtered DataFrame as an argument, matching `render_playstyle_explorer(filtered_df, ...)` and `render_h2h_section(filtered_df)`.

## 5. Charts

- All charts are built in `charts.py` as pure functions returning a Plotly `Figure`, then rendered in `app.py` via `st.plotly_chart(fig, width="stretch")`. **Never build a Plotly figure inline inside `app.py`** — this separation keeps charts independently testable (see `TESTING_GUIDE.md`) and keeps `app.py` focused on orchestration.
- `template="plotly_dark"` is used on every chart — keep this consistent for visual coherence; a future light-mode toggle would need to parameterize this, not hardcode a second template ad hoc in one chart function.
- Use `width="stretch"` (the current Streamlit API, replacing the deprecated `use_container_width=True`) on every `st.plotly_chart` call — already consistent throughout `app.py`.

## 6. Tables

- `st.dataframe(..., width="stretch", hide_index=True)` with a synthetic `#` row-number column added by `features.format_display_table` — keep this pattern for any new tabular display; don't expose pandas' default integer index to the user.
- Column labels are always the human-friendly versions (`DISPLAY_COLUMN_LABELS` in `features.py`), never raw snake_case column names. Any new displayed column must have an entry added to `FRIENDLY_NAMES`/`DISPLAY_COLUMN_LABELS`.

## 7. Performance

- **Caching is mandatory** for anything that reads the CSV or runs clustering — `@st.cache_data` is already applied to `load_and_clean_data`, `get_clustered_data`, and `load_app_data`. Any new expensive, deterministic, filepath-or-parameter-keyed computation must be cached the same way.
- **Never cache a function whose output depends on live widget state** (filters, search query) — correctly, `filter_dataframe`/`apply_search_filter` are *not* cached today, since they run on every rerun with fresh user input. Do not "optimize" this by caching filter results; Streamlit's cache would either be wrong (stale) or provide no benefit (cache key changes every keystroke).
- See `PERFORMANCE_GUIDE.md` for the deeper caching/rerun discussion.

## 8. Session State

- Not currently used (see `ARCHITECTURE.md §6`, `DECISIONS.md` ADR-006). If introduced, `st.session_state` keys must be namespaced clearly (e.g. `"h2h_player1"`, not `"player1"`) to avoid collisions as the app grows, and their purpose documented inline.

## 9. Accessibility

- Every input widget has a visible, descriptive label (`st.text_input("Type a player's name to filter the table:", "")`, `st.selectbox("Select Player 1:", ...)`) — never use `label_visibility="collapsed"` without an adjacent visible heading providing equivalent context.
- Color is never the *only* signal — the Playstyle Explorer's distribution chart uses both color and axis position/text labels; the H2H radar uses both distinct colors (`#00d2ff` / `#ff007f`) and a legend with player names. Preserve this redundancy in any new chart.
- Warnings that affect data interpretation (e.g. `st.warning("Comparing a goalkeeper to an outfield player — percentiles use different position pools.")`) must remain adjacent to the content they qualify, not buried elsewhere on the page.

## 10. Responsiveness

- `st.columns([...])` is used for side-by-side layout (metric comparisons, radar + player list) and adapts to Streamlit's built-in responsive breakpoints — no custom CSS/media queries exist or are needed at this scale. Do not introduce raw HTML/CSS layout hacks; use Streamlit's native layout primitives (`st.columns`, `st.container`) exclusively, matching current practice.

## 11. Loading Indicators

- `with st.spinner("Loading dataset and calculating playstyles..."):` wraps the initial data load — the **only** slow operation in the app (clustering + CSV read on cold cache). Any future operation that can take more than ~1 second (e.g. a live scrape, a large multi-season load) must be wrapped in an equivalent `st.spinner` with a specific, honest message — never a generic "Loading...".

## 12. Error Messages

- Current gap: `load_app_data("data/players_data_light-2025_2026.csv")` previously had no error handling — a missing file crashes the whole app with a raw traceback (see `STYLE_GUIDE.md §9`, `SECURITY_GUIDE.md`). The standard for user-facing errors going forward:
  - Wrap risky I/O in `try/except`.
  - On failure, use `st.error("Could not load the player dataset. Please check that the data file is present.")` (or similarly specific) and `st.stop()` to halt further rendering — never let the script continue with a `None`/empty DataFrame and produce a cascade of confusing secondary errors.
- Empty-result states are already handled well and should be the template for new sections: `st.info("No playstyle profiles available for the current filters.")`, `st.info("Select a broader filter set to compare at least two players.")`, `st.info("Not enough performance stats available to generate a scatter plot.")` — always a `st.info`, always specific about *why* nothing is showing and, where possible, what the user can do about it.

## 13. Professional Design Standards

- Chart titles are always product-facing, plain-English (e.g. "Elite Outlier Analysis: {x} vs {y}", "Percentile Footprint: {p1} vs {p2}") — never a raw column name or generic "Chart 1". Maintain this for any new visualization.
- Metric deltas (`st.metric(..., delta=round(diff, 2))` in the H2H section) always round to 2 decimal places for display — keep this consistent for any new numeric display to avoid noisy floating-point tails.
- Section headers read like a sports-analytics product ("Head-to-Head Player Comparison", "Elite Player Scatter Plot Comparison"), not like internal engineering names ("H2H Module", "Scatter Debug View"). Any new section name must pass this bar.
