# SEAD Strucke Data Cleaning — v1 pipeline (active)

Transformation pipeline for the current dataset revision, `data/StruckeC14_Sweden_v1.csv`. Species
and material taxonomy resolution happens live, every run, via
[`shared/resolution/`](../shared/resolution/) against `sead_staging`. This workspace is
self-contained.

## Structure

```
data/
  StruckeC14_Sweden_v1.csv        raw dataset (gitignored, ~14MB)
  manual_resolutions/              TRACKED - the hand-curated decisions the pipeline runs on
    species_manual_resolution.csv    manual_species -> resolved_order/family/genus/species +
                                      common_name_text/language, one row per distinct species
                                      value seen in the dataset.
    material_manual_resolution.csv   material -> up to 3 sead_element_N names + an optional
                                      sead_modification_type, under a real sead_record_type_id.
    species_token_corrections.csv    species_split -> manual_species correction table (typos
                                      fixed, duplicates merged, uncertain calls marked `?`).
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

The pipeline aims to tackle a problem that, although possible to solve through shapeshifter, would require taking care splitting values and manually resolving certain types of species, which could become a painful task to do through shapeshifter.

This is a faster way as of today for me to implement my knowledge. For example, the process of melting the rows is possible thanks to the Unnest feature in ShapeShifter, but for the process of melting species -> mapping to a manual resolution (requires already to have a mapping dict) -> re-melt, this is a faster path for implementation on my side.

On the journey to resolve this columns, I have tried to reconciliate the data to that of SEAD (for species and materials).  This will be done in ShapeShifter as part of the authority service needed to ensure data quality, but worth having it as there is connections between taxons and common_names to be done in a near future.

## Setup

Same `.env`/`requirements.txt` as the rest of the repo - both live at the true repo root, two
levels above `notebooks/` here. Notebooks are meant to be run from within `current/notebooks/`
(Jupyter's default working directory).
