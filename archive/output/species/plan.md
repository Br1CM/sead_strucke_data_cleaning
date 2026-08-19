# Species ETL: manual mapping → SEAD taxon/common-name matches

## Context

`output/species_split_taxa_gbif_matches.csv` (411 rows) is the previous automated match of
raw `species_split` tokens against SEAD taxonomy + GBIF, built in `notebooks/species_study.ipynb`.
Many rows are unmatched (237) or ambiguous (20) because the raw tokens are misspellings,
duplicates, or compound Swedish names the heuristics couldn't resolve.

The user has since hand-built `data/species_split_counts_in_original_manual.csv`, mapping every
`species_split` token to a corrected `manual_species` value (typos fixed, duplicates merged,
uncertain calls marked with a trailing `?`, and a few tokens split into multiple candidate species
via commas, e.g. `"brödvete, kubbvete"`). This is a cleaner, smaller vocabulary that deserves its
own fresh match against SEAD + GBIF rather than inheriting the old per-token results as-is.

Goal: build `notebooks/species_etl.ipynb` that (1) produces the deduplicated/re-split
`manual_species` vocabulary with correct counts, (2) carries over whatever GBIF info already
exists for it, (3) tries a direct SEAD match (common name, then Latin genus/family/order tables)
on the corrected spelling before touching the network, (4) fills remaining gaps with fresh GBIF
lookups, and (5) resolves/proposes SEAD `taxon_id`/`common_name_id` for every row that now has a
taxonomic anchor — flagging the rest for manual review rather than guessing. The `sead_staging` DB
connection available in this session is **read-only**, so step 5's output is a proposal (new IDs
computed as `max(existing_id)+1`, written to plain CSV) for later manual ingestion — no INSERTs
are executed.

## Existing patterns to reuse (from `notebooks/species_study.ipynb`)

- DB connection: `.env` + `sqlalchemy.create_engine("postgresql+psycopg2://...")`.
- SEAD lookups already coded there, to be reused/extended, not rewritten:
  - `sv_common` / `common_map` — Swedish common names joined to `view_taxa_alphabetically`
    (gives `taxon_id`, `genus`, `family`, `order`, `species` per common name).
  - `genus_hierarchy`, `family_hierarchy`, `order_hierarchy` — lowercased Latin-name lookups.
  - `match_exact()` — tries common name first, then Latin genus/family/order tables in that
    order; `infer_genus_by_suffix()`, `match_animal()` + `ANIMAL_LATIN` dict,
    `NON_TAXONOMIC_BLOCKLIST`, `strip_latin_qualifiers()`.
  - `gbif_match()` (species/match by scientific name + kingdom), `gbif_english_name()`
    (vernacular names by usageKey), both using a shared `requests.Session()`.
- Confirmed DB facts (queried live this session):
  - `tbl_taxa_tree_master(taxon_id, genus_id, species, author_id)`,
    `tbl_taxa_tree_genera(genus_id, genus_name, family_id)`,
    `tbl_taxa_tree_families(family_id, family_name, order_id)`,
    `tbl_taxa_tree_orders(order_id, order_name)`,
    `tbl_taxa_common_names(taxon_common_name_id, common_name, taxon_id, language_id)`,
    `language_id`: 1=English, 2=Swedish. No `kingdom` column anywhere — inferred manually as in
    the existing notebook.
  - Current max IDs: `taxon_id`=47009, `genus_id`=16751, `family_id`=1992, `order_id`=140,
    `taxon_common_name_id`=4272. New proposed IDs continue from these.
  - "Indeterminate" precedent (only one example in the whole DB): family `Cyperaceae` has no
    genus-level ambiguity handling except one placeholder genus named `"Cyperaceae indet"`
    (`genus_id=9810`) holding one taxon with `species='indet'`. No family/order-level "indet"
    naming exists yet — so when we must fabricate a placeholder above genus level, we extend the
    same `"<parent name> indet"` pattern downward (e.g. unknown genus under a known family →
    genus `"<Family> indet"`; that genus's taxon → `species='indet.'`).

## Steps to build in `notebooks/species_etl.ipynb`

### Setup
- New folder `output/species/` for all outputs of this notebook.
- Same imports/DB connection pattern as `species_study.ipynb`.
- First action after plan approval: write this plan to `output/species/plan.md` for reference
  alongside the notebook's outputs.

### 1. Re-derive the manual vocabulary + counts → `output/species/manual_species_count.csv`
- Load `data/species_split_counts_in_original_manual.csv` (`species_split`, `manual_species`, `count`).
- Split any `manual_species` containing commas into multiple rows (strip whitespace), **each
  getting the full original `count`, not divided** — matches the existing convention (a raw value
  like `"vete, spelt/emmer"` already counts toward every candidate, not fractionally).
- Keep trailing `?` markers as part of the value (e.g. `sol?` stays distinct from `sol`) — these
  remain flagged for later question, not merged with their unmarked counterpart.
- **Keep the blank row** (`species_split`/`manual_species` both empty, count 2 in the source) —
  don't drop it. It represents rows with no species value at all and is useful downstream as an
  explicit "no value" count, same role as the `<NA>` row in the old `species_study.ipynb` counts.
- Group by the resulting `manual_species` (treating blank as its own group) and sum `count` — this
  is where the recount happens: multiple old `species_split` tokens collapsing onto one corrected
  name, e.g. `al`, `albark`, `alknopp`, `alkottar`, `alkotte` → `al`.
- Save distinct `manual_species` + summed `count` to `output/species/manual_species_count.csv`.
- Also keep the intermediate long table in memory (`species_split` → `manual_species` → original
  row `count`) — needed for the GBIF carry-over join in step 2.

### 2. Carry over existing GBIF/match info → `output/species/manual_species_taxa_gbif_matches.csv`
- Left-join the long table from step 1 onto `output/species_split_taxa_gbif_matches.csv` on the
  **original** `species_split` key, bringing in `match_level`, `genus`, `family`, `order`,
  `sead_common_name`, `sead_species_name`, `kingdom`, all `gbif_*` columns.
- Collapse to one row per `manual_species`: where multiple contributing `species_split` rows exist,
  prefer the one with a non-null `gbif_usage_key`; if more than one contributor has a non-null,
  conflicting match, print a diagnostic table (don't silently drop it) and keep the first for now.
- Save to `output/species/manual_species_taxa_gbif_matches.csv`.

### 3. Direct SEAD match on the corrected spelling (before any GBIF calls)
- For every `manual_species` row, regardless of whether step 2 carried anything over, run the
  reused SEAD matchers directly against the corrected text: `match_animal()` first (Swedish animal
  vernacular → SEAD/Latin), then `match_exact()` (SEAD common-name table first, then the Latin
  genus/family/order tables), then `infer_genus_by_suffix()`. The corrected spelling may now match
  where the old raw/typo'd token didn't — this is a real second attempt, not just a copy of step 2.
- Where this direct match disagrees with what step 2 carried over, prefer the direct match (it's
  running against the corrected value) but log the disagreement for a quick sanity check.
- Update the working table in place with whatever this resolves.

### 4. Fill remaining GBIF gaps
- For every `manual_species` still missing a `gbif_usage_key` after steps 2–3, attempt fresh GBIF
  lookups on the cleaned Swedish term:
  - `species/match` (in case the corrected spelling now resolves in GBIF's backbone too).
  - A vernacular/free-text fallback — try `GET /v1/species/search?q=<term>` when `species/match`
    finds nothing; keep the top result's genus/family/order if it's a plausible match, and note
    which route produced the hit.
  - Terms that are actually artifacts/material categories, not organisms (e.g. `amulettring`,
    `stål`, `kalkbruk`, `ull`, `textil`) are expected to legitimately return nothing — no
    special-casing needed, they just stay unmatched.

### 5. Resolve/propose SEAD `taxon_id` + `common_name_id`
For every `manual_species` row that now has a taxonomic anchor (species/genus/family/order Latin
name), from step 2's carryover, step 3's direct match, or step 4's GBIF fallback:

- **a.** If a SEAD taxon already exists at that rank *and* its `taxon_id` already has a Swedish
  common name in `tbl_taxa_common_names` — done, record the existing `taxon_id` +
  `taxon_common_name_id`.
- **b.** If the taxon exists but has no common name yet, the `manual_species` text itself *is* the
  correct Swedish common name to assign — propose it as a new `tbl_taxa_common_names` row
  (`language_id=2`) with a new `taxon_common_name_id`.
- **c./d.** If only a higher rank (genus/family/order) is known: look for an existing
  "indeterminate" taxon already linked under that rank (`species` starting with `indet`, per the
  `Cyperaceae indet` precedent). Use it if found, then apply a./b. to it.
- **e.** If no such placeholder exists, or the rank itself doesn't exist in SEAD yet, fabricate the
  missing chain top-down (new `order`/`family`/`genus` as needed, named `"<parent> indet"` for the
  unknown levels), then a new `taxon` (`species='indet.'`) under it. New IDs = running
  `max(existing_id, already-proposed-this-run)+1`, deduplicated within the run so two rows needing
  the same placeholder reuse one proposed record instead of duplicating it.
- **f.** Assign the common name (`manual_species` text) to the resolved/created `taxon_id`.
- **Flag for manual review** (`needs_manual_review=True` + `review_reason`) instead of
  auto-assigning, when: no GBIF match and no SEAD match exists at any rank (nothing to anchor to),
  a genus-suffix inference is still ambiguous even after the GBIF cross-check, or the GBIF match
  confidence/type is weak. These rows still get a row in the output with whatever partial info was
  found, just no fabricated ID.
- Outputs:
  - `output/species/manual_species_sead_taxa_matches.csv` — one row per `manual_species` (including
    the blank/no-value row from step 1): all carried/direct/fresh match columns, plus `taxon_id`,
    `taxon_id_is_new`, `common_name_id`, `common_name_id_is_new`, `needs_manual_review`,
    `review_reason`.
  - `output/species/new_sead_records.csv` — every fabricated order/family/genus/taxon/common_name
    row proposed above (columns: `table`, proposed id column, name/value, parent id), reading as a
    to-do list for whoever later runs the real INSERTs.

## Verification
- Run the notebook top to bottom; confirm no exceptions.
- Sanity totals: `manual_species_count.csv['count'].sum()` should roughly match the sum in the
  source manual CSV (accounting for the intentional non-division on comma-splits), and the blank
  row's count should still be visible/traceable in the output.
- Spot-check a handful of known rows end-to-end: e.g. `al` (existing SEAD common name, case a),
  `säl` (family-level animal, case c/d/e), a currently-empty-match row (e.g. `amulettring`) ends up
  flagged for manual review rather than assigned a fake taxon.
- Print final counts: rows resolved via existing SEAD match, rows resolved via newly-proposed SEAD
  records, rows left for manual review.
