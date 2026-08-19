# SEAD Strucke Data Cleaning — v08 pipeline (historical)

This is the complete, frozen body of work built against the first dataset revision,
`data/c14_master_v08.xlsx`. It's preserved here exactly as it stood when the `StruckeC14_Sweden_v1.csv`
revision arrived and superseded it — kept for reference and for re-running if something about the
new revision's assumptions ever needs to be checked against the old one.

**This workspace is not maintained going forward.** New work happens in [`current/`](../current/);
the resolution logic it shares with this pipeline now lives in [`shared/`](../shared/). See the
[root README](../README.md) for how the three spaces fit together.

## Structure

```
data/                       source spreadsheet and manual mapping/resolution CSVs (not tracked in git)
notebooks/
  explore.ipynb               first pass over the raw dataset: shape, C14/calibration
                               fields, author normalization, unique (material, species)
                               extraction, lab_no-to-tbl_dating_labs matching
  sites_id_study.ipynb        matches site_id/raa_id against sead_staging tbl_sites
  context_feature_matching.ipynb
                               approaches matching Strucke's context values to SEAD features
  biblio_matching.ipynb        matches Strucke's (title, author, publication_year) references
                               against sead_staging tbl_biblio: exact on normalized title, then
                               TF-IDF/character-n-gram cosine similarity for fuzzy candidates,
                               corroborated by author-string similarity and a magnet-title check
  material_species_taxa_matching.ipynb
                               matches the dataset's (material, species) tuples against the
                               sead_staging taxa tables
  species_study.ipynb          splits/melts/counts the species column, then matches each
                               split value against SEAD's taxonomy + GBIF
  species_split_for_study_etl.ipynb
                               takes the manually-corrected species mapping and resolves
                               real-or-new SEAD taxon_id/common_name_id for each one
                               (author_id-aware: only reuses a SEAD taxon whose author_id
                               is NULL, otherwise proposes a fresh one)
  material_counts.ipynb        counts unique raw `material` values
  c14_dataset_tranformation.ipynb
                               the main pipeline: melts the resolved species taxonomy onto
                               c14_master_v08.xlsx (one species per row), resolves and melts
                               material elements/modifications (one material element per
                               row), then resolves and melts the measured-value columns
                               (one measured value per row, each with its own SEAD
                               method_id) - every transformation builds on the last, so a
                               single row always identifies one species + one material
                               element + one measured value. This is the only pipeline that
                               reaches the measurement melt - `current/`'s v1 pipeline stops
                               one step earlier (species + material only).
scripts/                    standalone scripts that reproduce specific notebook outputs
  build_author_normalization_review.py
  build_material_species_taxa_match_v2.py
comparisons/                 Excel-vs-SEAD column comparisons (see comparisons/README.md);
                               built against c14_master_v08.xlsx columns specifically
output/                     generated CSVs (mostly gitignored, see below)
  species/                    species-resolution artifacts (manual_species_count,
                               manual_species_taxa_gbif_matches, manual_species_sead_taxa_matches,
                               new_sead_records, plan.md) - manual_species_resolved_with_ids_v4_6.csv
                               is the final species-resolution artifact this pipeline produced
  material/                   material-resolution artifacts (material_counts,
                               material_counts_resolved_with_ids, new_sead_records_material) -
                               material_counts_resolved_with_ids_v4_3.csv is the final one
  measurements/                new_sead_records_measurements (proposed new methods/units)
  lab_no/                     lab_no_prefix_matches.csv - lab_no prefix to tbl_dating_labs
                               dating_lab_id mapping, for manual review
  biblio/                     biblio_reference_matches.csv - (title, author, year) to
                               tbl_biblio biblio_id mapping, for manual review
  mod_dataset/                 the fully melted c14 datasets - the actual ingestion-ready output
```

Outputs are versioned rather than overwritten: filenames carry the manual-mapping revision they
were built from (e.g. `_v4`), and re-running a notebook against an unchanged revision appends a
numeric suffix (`_2`, `_3`, ...) instead of clobbering a previous run. The full run history is kept
as-is here, nothing pruned.

## Setup

Same `.env`/`requirements.txt` as the rest of the repo - both live at the true repo root, one level
above this folder. Notebooks here already account for that (`load_dotenv()` walks up the directory
tree by default; the two places that hardcoded a relative `.env` path use `../../.env`).

Notebooks are meant to be run from within `archive/notebooks/` (Jupyter's default working
directory); the scripts in `archive/scripts/` can be run from anywhere.

## Outputs

Everything under `output/` is generated by the notebooks/scripts and is gitignored by default,
since most of it is intermediate or scratch. Explicitly tracked (as of now):

- `output/author_normalization_review.csv`
- `output/material_species_taxa_match_v2.csv`
- `output/context_type_unmatched.csv`
- `output/species/manual_species_sead_taxa_matches_v*.csv` (only the latest revision stays
  un-ignored at a time - see the root `.gitignore`)
- `output/species/plan.md`

Two files in `output/` predate the current notebook code and aren't reproducible by name from it -
kept for the historical record rather than deleted: `mod_dataset/c14_master_v08_melted_v4_4.csv`
and `species_unique_raw_and_split_with_taxa.{csv,xlsx}`. `data/reviewed_parishes_v1.csv` is
likewise unused by any current notebook - staged for a parish/site resolution step that was never
wired in.
