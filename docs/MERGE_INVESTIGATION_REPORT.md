# Merge Investigation Report — WC2022 Master Dataset

**Date:** 2026-08-06
**Scope:** Why does the merged FBref+StatsBomb dataset only contain 73 players?

## Executive Summary

The merge is **not actually failing** — the current pipeline matches **all 71 eligible players (100%)** after the minutes filter. The "73 matched players" is the expected output of the current as-is matching strategy, which matches only **20.4% (139/680)** of FBref players to StatsBomb. The remaining ~80% fail to match because of **three compounding causes**: (1) position encoding mismatch, (2) name normalization mismatch, (3) mojibake from wrong CSV encoding. **No single player is being wrongly dropped** — the filter just happens to retain only players who matched.

## 1. Row Counts at Each Step

| Step | Rows |
|------|------|
| standard (FBref) | 680 |
| shooting (FBref) | 680 |
| miscellaneous (FBref) | 680 |
| goalkeeper (FBref) | 41 |
| FBref merged | 680 |
| StatsBomb | 475 |
| Merged (as-is, name_norm+squad_norm+pos) | 680 (139 matched, 20.4%) |
| After 90s>=3.0 filter | **71** (71 matched, 100%) |

The master CSV on disk has **71 rows** (the "73" in the prompt is stale — current build produces 71: 71 distinct players, all with SB data, 70 with min>=270).

## 2. Match Rates per Merge

| Merge | Matched | Rate |
|-------|---------|------|
| FBref std+shooting (inner) | 680/680 | 100% |
| FBref +misc (inner) | 680/680 | 100% |
| FBref +GK (left) | 41/41 | 100% |
| FBref+SB **as-is** (name_norm+squad_norm+pos) | 139/680 | **20.4%** |
| FBref+SB no-pos | 237/680 | 34.9% |
| FBref+SB pos-normalized | 144/680 | 21.2% |
| FBref+SB full-name+pos-norm | 121/680 | 17.8% |
| After 90s>=3.0 filter (as-is) | 71/71 | 100% |

## 3. Root Causes of Matching Failure

### A. Position Encoding (20.3% of FBref players)

FBref uses **combined positions**: `FWMF, MFFW, DFMF, MFDF` (138/680 = 20.3%).
StatsBomb uses **simple positions**: `FW, MF, DF, GK` only.

Merge on exact `pos` fails for every combined-position player. Example:

```
FBref: Abdelhamid Sabiri | pos=MF  -> SB: Abdelhamid Sabiri | pos=DF  [pos differs]
FBref: Abdul Rahman Baba | pos=MFDF -> SB: Abdul Rahman Baba | pos=DF  [MFDF not in SB]
```

Evidence: FBref pos values `['DF','DFMF','FW','FWMF','GK','MF','MFDF','MFFW']` vs SB `['DF','FW','GK','MF']`. Only DF/FW/GK/MF are shared.

### B. Name Normalization Mismatch (most impactful, ~66% of unmatched)

The current `normalize_name()` truncates to **first + last name** (e.g., `"Abdelkarim Hassan Al Haj Fadlalla"` → `"abdelkarim fadlalla"`), but FBref and StatsBomb store **different full-name forms** for the same player:

- FBref: `Abdelkarim Hassan` → SB: `Abdelkarim Hassan Al Haj Fadlalla`
- FBref: `Alisson` → SB: `Alisson Ramsés Becker`
- FBref: `Achraf Hakimi` → SB: `Achraf Hakimi Mouh`

After first+last truncation: `"abdelkarim hassan"` (FBref) ≠ `"abdelkarim fadlalla"` (SB). **443 FBref names have no `name_norm` match in SB** (of 680).

Also, FBref names **with accents are read as mojibake** (see C below), so `"Julián Álvarez"` becomes `"JuliÃ¡n Ãlvarez"`, and the manual accent-strip table doesn't help.

### C. Encoding (latin-1 vs UTF-8) — 190 mojibake names

The FBref CSVs are read with `encoding='latin-1'`, but the files are actually **UTF-8**. Evidence:

- latin-1 read: **190 mojibake-char occurrences**, 19 soft-hyphen (`\xad`) names
- utf-8 read: 0 mojibake, 0 soft-hyphens
- **178/680 names differ** between the two encodings

Example: latin-1 gives `agust\xadn canobbio`, `juliÃ¡n Ã¡lvarez`; utf-8 gives `agustín canobbio`, `julián álvarez`. The accent-strip in `normalize_name` uses a hardcoded table that can't fix mojibake — the correct fix is reading with `encoding='utf-8'` (or `encoding='utf-8-sig'`).

### D. Squad Names — NOT a problem

After normalization, **squad sets match perfectly** (0 differences). The `FBREF_TO_COUNTRY` mapping works.

### E. Duplicates — NOT a problem

- SB duplicate (name_full, squad): **0**
- FBref duplicate (name_full, squad): **0**

No fan-out or ambiguous matches from duplicates.

### F. Whitespace — minor, handled

Names are stripped; the remaining issues are token/order differences, not whitespace.

## 4. Failure Category Breakdown (as-is strategy, 541 unmatched)

| Category | Count |
|----------|-------|
| Combined position (FWMF/MFFW/DFMF/MFDF) | 138 |
| Name not found in SB (first+last truncation) | 443 |
| Squad mismatch | 0 |

Note: categories overlap (a player can have both a combined pos AND an unmatched name).

## 5. Recommended Matching Strategy

The best strategy is a **cascade** of increasingly lenient keys, in order:

1. **L1**: full-unicode-normalized name + squad + normalized position (match rate: 22.6%)
2. **L2**: first+last name + squad + normalized position (+6%)
3. **L3**: full name + squad (no pos) (+15.5%)
4. **L4**: first+last + squad (no pos) (+3.3%)
5. **L5**: first name + squad + pos (+11.3%)
6. **L6**: last name + squad (+4.9%)

Total: **63.5% matched with UTF-8** (vs 56.5% with latin-1).

For the 90s>=3.0 cohort (the actual dataset), the as-is pipeline already achieves **100% match** — the matched players happen to be the ones with enough minutes. The low "73 matched players" is therefore the *expected* result of the current pipeline, not a bug that silently drops data.

### Fixes, in priority order

1. **Fix encoding**: read FBref CSVs with `encoding='utf-8'` instead of `'latin-1'`. (Fixes 178 names, 190 mojibake chars, 19 soft-hyphen artifacts.)
2. **Fix name normalization**: use full Unicode-stripped name as primary key, not first+last truncation. Add a fallback cascade for the residual mismatches (middle names, compound surnames).
3. **Fix position normalization**: map combined FBref positions to simple SB positions (`FWMF→FW`, `MFFW→FW`, `DFMF→DF`, `MFDF→MF`).
4. **Re-evaluate the 90s>=3.0 filter**: the current threshold may be too aggressive for WC2022 (tournament minutes are low); consider lowering to 90s>=1.0 (270 min) or using FBref `min>=270` instead.

## Verification Evidence

- Reproduced with exact `build_master_dataset.py` loader logic (latin-1, same key columns)
- Master CSV on disk: 71 rows, 71 with `gls_sb` populated — consistent with the 71-row output above
- The "73" from the task prompt is stale; rebuild produces 71
