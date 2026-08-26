# Reproducing Manual Resolution Cleaning in ShapeShifter

### A step-by-step guide — no coding required

## 1. Introduction

The current cleaning pipeline (`current/notebooks/c14_v1_dataset_transformation.ipynb`)
relies on five hand-curated CSV files under `current/data/manual_resolutions/`, plus
one regex-based text-extraction step, to clean up the Strucke C14 dataset:

| # | What it fixes | Source file |
|---|---|---|
| 1 | `landskap` (province) abbreviations/typos | `landskap_token_corrections.csv` |
| 2 | `lab_id` prefix extraction + lab name lookup | `lab_prefix_name_manual_resolution.csv` |
| 3 | Multi-value `lämningsnummer`/`uppdragsnummer` columns | (no CSV — a plain comma split) |
| 4 | `species` text split into tokens + canonical spelling | `species_token_corrections.csv` |
| 5 | `material` text split into components + translation | `material_manual_resolution.csv` |

This guide shows how to do the same cleaning directly in **ShapeShifter**'s web
interface, using its **Replace**, **Extra Columns**, and **Unnest** tabs — no Python,
no notebooks.

**Out of scope for this guide:** two later pipeline steps look up official SEAD
database IDs for species and material (matching against GBIF taxonomy data and a
live `sead_staging` database connection). Those steps are not covered here — see
[Section 6](#6-what-this-guide-does-not-cover).

**Ready-made mapping files:** for every recipe below, a ready-to-paste YAML file
already exists in [`shapeshifter_mappings/`](shapeshifter_mappings/), generated
directly from the real CSV data, so you don't have to retype hundreds of values by
hand. Each recipe tells you exactly which file to use and how.

## 2. Before You Start

This guide assumes you already have:

- A ShapeShifter project set up, with
- An **entity** created for the Strucke dataset (its CSV file already uploaded and
  attached to that entity).

You'll need to know the entity's name and the names of the columns you're working
with: `landskap`, `lab_id` (renamed `lab_nummer` by the pipeline), `species`,
`material`, and `lämningsnummer`/`uppdragsnummer`. If any of these don't exist yet,
set that up first (Files tab → upload → Entities tab → Add Entity) before
continuing.

## 3. Core Concept: The "Raw Value → Manual Value" Pattern

Every recipe below follows the same underlying idea, borrowed directly from how the
notebook pipeline works today:

1. Somebody looks at every distinct raw value in a column (e.g. every different way
   `landskap` was spelled) and decides, by hand, what the *correct* value should be.
2. That decision is written down as a lookup table: raw value → correct value.
3. The pipeline applies that lookup table to the whole dataset.
4. If a **brand-new** raw value shows up in a future data update — one nobody has
   reviewed yet — someone needs to notice and add a decision for it.

In the notebook, step 4 is enforced automatically: the pipeline **stops with an
error** the moment it meets an unmapped value. In ShapeShifter, step 4 works
differently — **nothing stops automatically**. You'll need to get in the habit of
checking for new values yourself. [Section 5](#5-finding-and-fixing-new-unmatched-values-ongoing-maintenance)
explains exactly how, and every recipe below links back to it — you only need to
read it once.

In ShapeShifter, the lookup table itself lives in the **Replace** tab of an entity,
as a rule with match type **`map`** — literally a list of "this raw value" →
"becomes this value" pairs, editable by hand or pasted in as a block.

## 4. Recipes

### 4a. Correcting `landskap` values

- **What this replaces:** `landskap_token_corrections.csv` (36 raw → corrected
  province-name pairs, e.g. `Bo` → `Bohuslän`, `Vs` → `Västmanland`).
- **ShapeShifter feature:** Replace tab, one `map` rule. This is the simplest
  recipe in the guide — a pure one-column lookup table, no regex needed.
- **Steps:**
  1. Open your entity, go to the **Replace** tab.
  2. Select the `landskap` column.
  3. Click **Add rule**, set the match type to **map**.
  4. Open [`shapeshifter_mappings/landskap_replacements.yml`](shapeshifter_mappings/landskap_replacements.yml)
     — it contains the full 36-pair list, ready to use. Either:
     - Switch to the entity's **YAML** tab and paste the whole `replacements:`
       block in directly (fastest), or
     - Re-type each `raw: corrected` pair into the "Add rule" form by hand, using
       the file as your reference list.
  5. Save.
- **How to check it worked:** open the data preview for this entity and scan the
  `landskap` column — every value should now be a full province name, no
  abbreviations.
- **Gotchas:** none — this is the template the harder recipes below build on.

### 4b. Extracting and resolving lab ID prefixes

- **What this replaces:** the regex logic in `shared/resolution/lab.py::lab_id_prefix()`
  plus `lab_prefix_name_manual_resolution.csv` (50 prefix → corrected code/lab-name
  pairs, e.g. `Ua-49252` → prefix `Ua` → `Ua` / *Uppsala Accelerator*; `12C/0126` →
  no leading letters → `Unknown` / *Unknown or unspecified*).
- **ShapeShifter feature:** Extra Columns (to extract the prefix with
  `regex_extract`) + Replace (to look up the corrected code/name), chained
  together. This is the hardest recipe in the guide — several small steps stacked
  together to equal one Python function. **That's expected, not a sign you've done
  something wrong.**
- **Steps:**
  1. Open [`shapeshifter_mappings/lab_prefix_replacements.yml`](shapeshifter_mappings/lab_prefix_replacements.yml)
     — it contains everything for this recipe, fully commented.
  2. Go to the **Extra Columns** tab and paste in the `extra_columns:` block from
     that file. In order, it:
     - strips the "Okänd###" (unknown sample number) placeholder text first, so it
       isn't mistaken for a lab code;
     - extracts leading letters from the start of the ID (the normal case, e.g.
       `Ua` from `Ua-49252`);
     - as a fallback, extracts any letters found *anywhere* in the ID, for the
       oddly-formatted ones (e.g. the `C` in `12C/0126`);
     - combines those into one `lab_id_prefix` column that mirrors the original
       CSV's categories;
     - duplicates that column twice, into `lab_prefix_raw` and `lab_name_raw` — one
       copy per thing we want to look up (see the note below on why).
  3. Go to the **Replace** tab (or the YAML tab) and paste in the `replacements:`
     block from the same file. It applies one `map` lookup to `lab_prefix_raw`
     (giving you the corrected prefix code) and a second, independent `map` lookup
     to `lab_name_raw` (giving you the full lab name).
  4. Save.
- **Why two duplicate columns?** A ShapeShifter Replace rule can only rewrite the
  column it's attached to — it can't take one input and write out to two different
  destination columns. Duplicating the column first, then applying a different
  lookup to each copy, is the standard way around that.
- **How to check it worked:** preview the entity — you should see `lab_prefix_raw`
  showing corrected codes like `Ua`, `GrN`, `KIA`, and `lab_name_raw` showing full
  lab names.
- **Gotchas:**
  - If the Replace tab won't let you pick `lab_prefix_raw`/`lab_name_raw` yet, save
    and preview once first so the new Extra Columns actually exist, then add the
    Replace rules.
  - Known limitation: this recipe cannot perfectly reproduce one rare edge case —
    a lab ID with *no letters anywhere* that also isn't the "Okänd" placeholder
    text (e.g. a bare number). ShapeShifter's formula language has no if/else
    logic, so this one case falls back to the generic "no lab given" result
    instead of the more specific tag the notebook produces. This does not affect
    any lab ID actually seen in the current dataset — only a note for future data.

### 4c. Splitting multi-value columns (`lämningsnummer` / `uppdragsnummer`)

- **What this replaces:** a handful of rows pack more than one site/project ID into
  a single comma-separated cell (e.g. `L2016:9874, L2015:343`).
- **ShapeShifter feature:** this one is **not** a job for Unnest by itself — despite
  the name, Unnest only turns *already-separate columns* into rows (like Excel's
  "unpivot"); it doesn't split a single delimited string. So the recipe is: first
  pull the comma-separated parts into their own columns, *then* Unnest those
  columns into rows.
  1. Go to **Extra Columns** and create one column per expected part, using
     `regex_extract`, e.g.:
     ```yaml
     extra_columns:
       lamningsnummer_1: "=trim(regex_extract(lamningsnummer, '^[^,]+', 0))"
       lamningsnummer_2: "=trim(regex_extract(lamningsnummer, ',\\s*([^,]+)', 1))"
     ```
     (add a `_3` if you find a row with three values — check the data preview for
     the widest split needed).
  2. Go to the Unnest configuration and set:
     ```yaml
     unnest:
       id_vars: [<your other identifying columns>]
       value_vars: [lamningsnummer_1, lamningsnummer_2]
       var_name: lamningsnummer_part
       value_name: lamningsnummer_split
     ```
  3. Save and preview — row count should grow by one extra row for every
     comma-separated cell.
- **How to check it worked:** in the preview, find a site that originally had two
  IDs and confirm it now appears as two rows, each with one clean ID.
- **Gotchas:** unlike 4d below, there's no lookup/reconciliation step needed
  afterward — this is a pure fan-out, nothing to canonicalize.

### 4d. Splitting and reconciling species text

- **What this replaces:** the species column is lowercased, split on commas/slashes
  into individual tokens, melted into one row per token, then each token is looked
  up in `species_token_corrections.csv` (411 raw-token → canonical-species pairs)
  to fix typos, merge synonyms, and flag uncertain values.
- **ShapeShifter feature:** Extra Columns (split into token columns) → **Unnest**
  (melt into one row per token — this *is* the case Unnest is meant for, since by
  this point we already have separate columns to melt) → Replace (`map`, to
  canonicalize each token).
- **Steps:**
  1. Extra Columns: lowercase the species text —
     `species_lower: "=lower(species)"`.
  2. Replace tab: add a `regex_sub` rule on `species_lower` to strip stray digits
     and `?` characters (pattern `[0-9?]`, replace with nothing) — this matches
     the noise-stripping the notebook does before splitting.
  3. Extra Columns: split into up to 3 token columns (species text rarely has more
     than 3 comma/slash-separated parts — check your data preview to confirm):
     ```yaml
     extra_columns:
       species_1: "=trim(regex_extract(species_lower, '^[^,/]+', 0))"
       species_2: "=trim(regex_extract(species_lower, '[,/]\\s*([^,/]+)', 1))"
     ```
  4. Unnest:
     ```yaml
     unnest:
       id_vars: [<your other identifying columns>]
       value_vars: [species_1, species_2]
       var_name: species_part
       value_name: species_split
     ```
  5. Reconcile the token: open
     [`shapeshifter_mappings/species_replacements.yml`](shapeshifter_mappings/species_replacements.yml).
     With 410 pairs, **don't** try to enter this one via "Add rule" by hand —
     open the entity's **YAML** tab instead and paste the `replacements:` block
     directly. This is still not "programming" — you're pasting in a list, the
     same as pasting rows into a spreadsheet.
     - If you'd still rather use the point-and-click form despite the length, that
       works too — it's the exact same "Add rule" → match type "map" mechanic as
       recipe 4a, just repeated 410 times.
  6. Save.
- **How to check it worked:** preview and scan `manual_species` (or whatever you
  named the output) — misspellings and inflected forms (`albark`, `alkottar`,
  `alknopp`, …) should all now read the same canonical value (`al`).
- **Gotchas:**
  - **Known limitation:** 4 raw tokens in the source data legitimately correspond
    to *two* canonical species at once (e.g. `get alt. svin` → "goat or pig", both
    `get` and `svin`). A `map` rule can only produce one output per input, so these
    four are mapped to the same comma-joined text the CSV uses. To split those
    into two separate rows exactly like the original pipeline does, repeat the
    Unnest step a second time on the resulting column, splitting on comma — the
    mapping file lists exactly which 4 tokens these are.
  - Live SEAD taxonomy ID lookup (the next step in the notebook) needs a database
    connection and is out of scope here — see [Section 6](#6-what-this-guide-does-not-cover).

### 4e. Splitting material strings into components

- **What this replaces:** `material_manual_resolution.csv` — each of 42 raw
  `material` strings is split by hand into up to 3 components, translated to
  English, tagged with an optional modification note (e.g. "charred"), and given a
  SEAD element name.
- **ShapeShifter feature:** the same "duplicate the column, then apply an
  independent `map` to each duplicate" pattern as 4b — just with more outputs (up
  to 12 columns instead of 2), since one raw material string can drive several
  independent pieces of information.
- **Steps:**
  1. Open [`shapeshifter_mappings/material_replacements.yml`](shapeshifter_mappings/material_replacements.yml).
  2. Go to **Extra Columns** and paste in its `extra_columns:` block — it
     duplicates the `material` column once per output you need (split
     components, English translations, modification flag, SEAD element names).
  3. Go to the **Replace** tab (or the YAML tab — recommended, for the same reason
     as species: several of the columns have dozens of pairs) and paste in the
     `replacements:` block.
  4. Save.
- **How to check it worked:** preview and check that e.g. `material_split_1_raw`
  and `material_english_1_raw` line up correctly for a known row (raw material
  *"Förkolnat frö"* should show split `frö`, English `seed`, modification
  `Förkolnat`).
- **Gotchas:** the `material_sead_element_*` and `material_sead_modification_type`
  outputs are element/modification **names** (e.g. `"Bone(s)"`, `"Carbonised"`),
  not database IDs — matching those names to real SEAD database IDs is a
  live-database step, out of scope here (see [Section 6](#6-what-this-guide-does-not-cover)).

## 5. Finding and Fixing New Unmatched Values (Ongoing Maintenance)

Once your `map` rules are in place, this is the repeatable habit for keeping them
up to date as new data comes in — referenced from every recipe above instead of
repeated three times.

1. After adding your initial rules, run/re-run the entity.
2. Open the entity's **data preview**. There is no dedicated "unmatched values"
   panel for Replace rules in ShapeShifter (that only exists for a different,
   separate feature called Reconciliation) — so checking means **looking at the
   actual column values** in the preview: sort or scan the corrected column and
   look for anything that still reads like raw, uncorrected text (an abbreviation
   that should have expanded, a typo that should have been fixed, etc.).
3. For each new raw value you spot: decide what the canonical value should be —
   this is the same human judgment call the notebook process always required —
   then go back to **Add rule** (or edit the pasted `map` block) and add the new
   pair.
4. Re-run and re-check the preview to confirm it's now corrected.
5. **Important difference from the notebook to keep in mind:** in the notebook, a
   brand-new unmapped value stops the whole pipeline with an error until someone
   fixes the CSV — you can't miss it. In ShapeShifter, nothing stops automatically;
   an unmapped value just quietly passes through unchanged. Make checking the
   preview part of your routine every time you bring in new data, rather than
   assuming everything was caught.

## 6. What This Guide Does Not Cover

Two later steps in the notebook pipeline are intentionally left out of this guide:

- **Matching species names against GBIF's global taxonomy database** to help
  decide the correct scientific classification.
- **Looking up official SEAD database IDs** for resolved species and material
  element names (via a live connection to the `sead_staging` database).

Both of these are candidates for ShapeShifter's **Reconciliation** feature — a
more advanced, ID-matching tool with its own review workflow — which is planned as
a follow-up phase, not covered by this guide.

## 7. Quick Reference

| Recipe | Source file | ShapeShifter feature(s) | Tab(s) |
|---|---|---|---|
| 4a. Landskap correction | `landskap_token_corrections.csv` | Replace (`map`) | Replace |
| 4b. Lab ID prefix + name | `lab_prefix_name_manual_resolution.csv`, `shared/resolution/lab.py` | Extra Columns (`regex_extract`, `coalesce`) + Replace (`map`) | Extra Columns, Replace |
| 4c. Multi-value column split | *(no CSV — plain comma split)* | Extra Columns (`regex_extract`) + Unnest | Extra Columns, Unnest config |
| 4d. Species split + reconcile | `species_token_corrections.csv` | Extra Columns + Unnest + Replace (`map`) | Extra Columns, Unnest config, Replace/YAML |
| 4e. Material split | `material_manual_resolution.csv` | Extra Columns + Replace (`map`) | Extra Columns, Replace/YAML |
| Ongoing maintenance | — | Data preview | Preview panel |

**Mapping files:** [`shapeshifter_mappings/`](shapeshifter_mappings/) —
`landskap_replacements.yml`, `lab_prefix_replacements.yml`,
`species_replacements.yml`, `material_replacements.yml`.
