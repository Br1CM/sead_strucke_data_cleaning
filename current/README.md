# SEAD Strucke Data Cleaning — v1 pipeline (active)

Transformation pipeline for the current dataset revision, `data/StruckeC14_Sweden_v1.csv`. This
workspace is self-contained: it never reads from [`archive/`](../archive/) or from its own
`output/` at runtime. Species and material taxonomy resolution happens live, every run, via
[`shared/resolution/`](../shared/resolution/) against `sead_staging` - not by trusting a
previously-generated CSV.

## Why self-contained

The old pipeline (`archive/notebooks/c14_dataset_tranformation.ipynb`) wrote its species/material
id resolutions to `output/`, and this pipeline used to read those frozen files back in. That made
it fragile: reproducing the pipeline from a clean checkout required someone to have previously run
the old notebook and left its output CSVs lying around, un-tracked in git. Now the two things this
pipeline actually depends on for resolution are code (`shared/resolution/species.py`,
`shared/resolution/material.py`) and data (`data/manual_resolutions/`, tracked in git) - both
reproducible from a clean checkout plus a DB connection.

## Structure

```
data/
  StruckeC14_Sweden_v1.csv        raw dataset (gitignored, ~14MB)
  manual_resolutions/              TRACKED - the hand-curated decisions the pipeline runs on
    species_manual_resolution.csv    manual_species -> resolved_order/family/genus/species +
                                      common_name_text/language, one row per distinct species
                                      value seen in the dataset. Professionalized copy of
                                      archive/data/manual_species_resolved_test.csv - same
                                      decisions, cleaned-up columns (the stale taxon_id/
                                      common_name_id columns from the old draft were dropped;
                                      shared.resolution.species recomputes those live instead).
    material_manual_resolution.csv   material -> up to 3 sead_element_N names + an optional
                                      sead_modification_type, under a real sead_record_type_id.
                                      Professionalized copy of
                                      archive/data/material_counts_manual_resolved.csv (fixed a
                                      typo'd column header, otherwise unchanged).
    species_token_corrections.csv    species_split -> manual_species correction table (typos
                                      fixed, duplicates merged, uncertain calls marked `?`).
                                      Copy of archive/data/species_split_counts_in_original_manual_v4.csv.
notebooks/
  c14_v1_dataset_transformation.ipynb   the pipeline: load v1 csv -> rename columns -> split/melt
                                         species -> reconcile v1's species tokens against
                                         species_token_corrections.csv -> resolve SEAD species ids
                                         live (shared.resolution.species) -> resolve SEAD material
                                         element ids live (shared.resolution.material) -> melt
                                         material elements. No measurement melt yet (see below).
  manual_resolution_walkthrough.ipynb   documentation notebook: loads the three
                                         manual_resolutions/ CSVs, calls the shared resolution
                                         functions, and shows/explains the resulting SEAD id
                                         assignments and any newly-proposed records - a way to
                                         inspect the resolution step in isolation from the
                                         production pipeline.
output/                            write-only export target (gitignored) - never read back in
  mod_dataset/
    StruckeC14_Sweden_with_sead_taxonomy_v1.csv
    StruckeC14_Sweden_with_sead_taxonomy_and_material_v1.csv
    new_sead_records_species_v1.csv     proposed new SEAD taxonomy records (order/family/genus/
                                         taxon/common_name) - a to-do list, no INSERTs executed
    new_sead_records_material_v1.csv    proposed new SEAD abundance-element/modification-type records
```

## Scope

This pipeline stops at the material-element melt. The old pipeline's third melt (one measured
value per row, with its own SEAD `method_id`) hasn't been ported to v1 yet - that's future work,
tracked separately from this reorganization.

## Setup

Same `.env`/`requirements.txt` as the rest of the repo - both live at the true repo root, two
levels above `notebooks/` here. Notebooks are meant to be run from within `current/notebooks/`
(Jupyter's default working directory).
