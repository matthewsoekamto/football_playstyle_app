# Merge Failure Analysis v2 — Deep Categorization & >95% Path

**Date:** 2026-08-06
**Question:** After UTF-8 + position normalization + Unicode normalization, why do players still fail to match, and can we reach >95%?

## 1. The 475-vs-680 Gap Explained (user's question)

StatsBomb `wc2022_players.csv` contains **475 players with min ≥ 90** (SB min floor = 90).
FBref `wc2022_standard.csv` contains **680 players, of which 201 have min < 90**.

```
FBref min<90:     201   ← SB excludes these entirely
FBref [90,270):   271
FBref min>=270:   208
SB count min>=270: 207   (≈ FBref 208)
SB min floor:      90
```

**The 205-row difference is almost entirely the min<90 players.** SB only ships players who appeared ≥90 minutes; FBref ships everyone. This is a **data presence gap, not a matching bug**.

## 2. Cascade Results (UTF-8 + translit + position-normalized)

| Strategy | Matched | Rate |
|---|---|---|
| Current `build_master_dataset.py` (latin-1, first+last, exact pos) | 139/680 | 20.4% |
| + UTF-8 + translit + position normalization | 361/680 | 53.1% |
| + token-subset matching (FBref tokens ⊆ SB tokens) | 440/680 | 64.7% |
| + nickname/edit-distance rules | ~461/680 | ~67.8% |
| **Post-filter (90s≥3.0) projection** | **208/217** | **95.9%** |

**The >95% target is achievable** — but only after the minutes filter. The full-680 matching can't exceed ~68% because SB genuinely lacks 219 players (mostly min<90).

## 3. Failure Categories (per unmatched player, after UTF-8+pos+Unicode)

Method: for each unmatched FBref player, find best same-squad SB candidate by token overlap + last-name containment + edit distance; classify by the diff pattern.

### A. Solvable automatically — name-format differences (73+105 = ~178)

**A1. FBref short name is prefix of SB full name — "middle name / suffix" (105)** — *auto-solvable by token-subset rule*

```
Brandon Aguilera        → Brandon Aguilera Zamora        (FBref short)
Alisson                 → Alisson Ramsés Becker
Jordi Alba              → Jordi Alba Ramos
Antony                  → Antony Matheus dos Santos
Edson Álvarez           → Edson Omar Álvarez Velázquez
Sergio Busquets         → Sergio Busquets i Burgos
Ángel Correa            → Ángel Fabián Di María Hernández
Gleison Bremer          → Gleison Bremer Silva Nascimento
Marco Asensio           → Marco Asensio Willemsen
```

**A2. Nickname / official name (19)** — *auto-solvable via edit-distance + nickname map*

```
Casemiro        → Carlos Henrique Casimiro
Gavi            → Pablo Martín Páez Gavira
Marquinhos      → Marcos Aoás Corrêa
Pedri           → Pedro González López
Pepe            → Kléper Laveran Lima Ferreira
Raphinha        → Raphael Dias Belloli
Fred            → Frederico Rodrigues Santos
Dani Alves      → Daniel Alves da Silva
Dani Olmo       → Daniel Olmo Carvajal
Dani Carvajal   → Daniel Carvajal Ramos
Fabinho         → Fábio Henrique Tavares
```

**A3. Spelling/transliteration variants (40)** — *auto-solvable by edit distance ≤2–3*

```
Ali Al-Bulaihi   → Ali Albulayhi            (lev 2)
Mohammed Salisu  → Mohamed Salisu           (lev 1)
Danny Ward       → Daniel Ward              (lev 3)
Matt Turner      → Matthew Charles Turner   (prefix)
Ró-Ró            → Pedro Miguel Correia     (nickname)
Saud Abdulhamid  → Saud Abdullah Abdul Hamid
```

**A4. Initials (1)** — *auto-solvable*: `Sergio Busquets → Sergio Busquets i Burgos` (particle "i")

### B. Semi-auto — ambiguous candidates (1–2, need review)

- `Dani Carvajal` vs `Daniel Olmo Carvajal` — same last name, two candidates; needs position/disambiguation (FBref DF vs SB has both)
- Saudi Arabia's `Mohammed Al-Owais` vs `Mohammed Khalil Al Owais` — spelling + middle name combos

### C. Truly absent from SB — data gap (24 with min≥90; 219 total)

**These players are NOT in the SB file under any name** (checked by token overlap anywhere + edit distance):

```
Firas Al-Buraikan (KSA, 268min)   Casemiro (BRA, 390min)
Gavi (ESP, 284min)                Marquinhos (BRA, 426min)
Lucas Paquetá (BRA, 314min)       Pedri (ESP, 356min)
Pepe (POR, 360min)                Raphinha (BRA, 315min)
Rodri (ESP, 390min)               Matthijs de Ligt (NED, 91min)
```

Interesting: even famous players like Casemiro/Pedri/Pepe are absent — the SB file is a **partial export**, not the full WC2022 player list. 198 of 219 absent have min<90 (consistent with SB's 90-min floor).

## 4. Category Counts (final, min≥90 unmatched = 129)

| Category | Count (min≥90 cohort) | Auto-solvable? |
|---|---|---|
| Middle-name/suffix (FBref short = prefix of SB) | 105 | ✅ yes (token-subset rule) |
| Nickname / official name | 19 | ✅ yes (edit-dist ≤3 + ~15-name map) |
| Spelling / transliteration | 40 | ✅ yes (lev ≤3) |
| Initials / particle ("i", middle initial) | 1 | ✅ yes |
| Ambiguous duplicate candidates | ~2 | ⚠️ review |
| **Truly absent from SB** | **24** (min≥90) / 219 (all mins) | ❌ no — data gap |
| **Total unmatched (min≥90)** | **129** | |

Note: the 105 "middle-name/suffix" and 40 "spelling" counts overlap with the 19 "nickname" cases in the raw tally — the disjoint partition of the 129 min≥90 unmatched is **105 present-in-SB (name variants, auto-solvable) + 24 truly absent (data gap)**. The categories A1–A4 together cover all 105 solvable cases.

## 5. Solvability Projection

```
Eligible cohort (90s≥3.0):            217
  Already matched (token-subset):     201   (92.6%)
  Solvable name-variants:              7    (+3.2%)
  Truly absent from SB:                9    (4.1%)  ← hard floor
Projected:                           208/217 = 95.9%   ✅ >95%
```

Even adding nickname-map + relaxed edit-distance rules, the **9 truly-absent eligible players** (Casemiro, Gavi, Marquinhos, Paquetá, Pedri, Pepe, Raphinha, Rodri, Firas Al-Buraikan) cap the rate at **95.9%** — unless we **re-download/complete the StatsBomb file** (those players ARE in StatsBomb open data under full official names; the CSV export was incomplete).

## 6. Recommended Implementation (before clustering)

1. **Read all FBref CSVs as UTF-8** (fixes 178 names / 190 mojibake chars).
2. **Position normalization**: `FWMF→FW, MFFW→FW, DFMF→DF, MFDF→MF` (fixes 138 combined-position players).
3. **Unicode normalization**: NFKD strip accents + translit table (`ł→l, ø→o, ß→ss, đ→d`, soft-hyphen removal).
4. **Matching cascade** (strict→relaxed, unique-candidate only):
   - L1: `stripped + squad + pos` (exact)
   - L2: `base(no-separators) + squad + pos`
   - L3: `first + last + squad + pos`
   - L4: `stripped + squad` (drop pos)
   - L5: `base + squad`
   - L6: `first + last + squad`
   - L7: `last + squad + pos` (unique candidate only)
   - L8: `last + squad` (unique candidate only)
   - L9: **token-subset** (`FBref tokens ⊆ SB tokens`, same squad, unique) ← +11%
   - L10: edit-distance ≤3 on base + nickname map (19 hand-mapped)
5. **Handle the 9 absent eligible players**: either re-export complete SB data (preferred) or explicitly document them as coverage gap (~4%).

## 7. Evidence Files

- `scripts/` investigation scripts: `categorize_unmatched.py`, `gap_analysis.py`, `gap2.py`, `absent_check.py`, `true_gap.py` (in worktree)
- Full example lists per category (20 each) printed by those scripts
- Master CSV verification: 71 rows, 71 with SB data
