# SEAD Strucke Data Cleaning — v1 pipeline (active)

Transformation pipeline for the current dataset revision, `data/StruckeC14_Sweden_v1.csv`. Species,
material, and lab taxonomy resolution happens live, every run, via
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
    species_token_corrections.csv    species_split -> manual_species correction table (typos
                                      fixed, duplicates merged, uncertain calls marked `?`).
    material_manual_resolution.csv   material -> up to 3 sead_element_N names + an optional
                                      sead_modification_type, under a real sead_record_type_id.
    landskap_token_corrections.csv   landskap -> manual_landskap correction table (abbreviations/
                                      typos mapped to the full province name already present
                                      elsewhere in the column, e.g. `Bo` -> `Bohuslän`).
    lab_prefix_name_manual_resolution.csv   lab_id_prefix/lab_id_prefix_category -> standardized
                                      manual_prefix/manual_lab_name, hand-completed from
                                      exploration.ipynb's lab_id_prefix_matches.csv export and
                                      cross-checked against tbl_dating_labs and the labs' own
                                      published lists.
notebooks/
  exploration.ipynb                     EDA notebook: unique-value dumps for every raw column,
                                         plus ad-hoc investigations that fed the manual_resolutions/
                                         CSVs above - landskap abbreviations, lab_id <->
                                         tbl_dating_labs prefix matching, duplicated site_id/lab_id
                                         rows, and place_name/site_id groupings as candidates for
                                         sample_group_name/sample_name/dataset_name. Not part of the
                                         production pipeline; run ad hoc as new questions come up.
  c14_v1_dataset_transformation.ipynb   the pipeline (steps 1-10): load v1 csv -> rename columns
                                         -> split multi-valued lamningsnummer/uppdragsnummer ->
                                         correct landskap (shared.resolution isn't used here, a
                                         plain join against landskap_token_corrections.csv) ->
                                         resolve lab_nummer prefix/name (shared.resolution.lab) ->
                                         build a unique_row_identifier from lab_nummer -> split/melt
                                         species -> reconcile species tokens -> resolve SEAD species
                                         ids live (shared.resolution.species) -> resolve SEAD
                                         material element ids live (shared.resolution.material) ->
                                         melt material elements. No measurement melt yet (see below).
  manual_resolution_walkthrough.ipynb   documentation notebook: loads the manual_resolutions/
                                         CSVs, calls the shared resolution functions, and
                                         shows/explains the resulting SEAD id assignments and any
                                         newly-proposed records - a way to inspect the resolution
                                         step in isolation from the production pipeline.
output/                            write-only export target (gitignored) - never read back in
  mod_dataset/
    v1/, v1_2/, ...                  one folder per pipeline run (common.next_available_dir()
                                      never reuses a folder), each with:
      StruckeC14_Sweden_with_sead_taxonomy.csv
      StruckeC14_Sweden_with_sead_taxonomy_and_material.csv
      new_sead_records_species.csv     proposed new SEAD taxonomy records (order/family/genus/
                                        taxon/common_name) - a to-do list, no INSERTs executed
      new_sead_records_material.csv    proposed new SEAD abundance-element/modification-type
                                        records
  landskap/landskap_counts.csv       raw landskap value counts - exploration.ipynb's starting
                                      point for landskap_token_corrections.csv
  lab_id/lab_id_prefix_matches.csv(.xlsx)   per-prefix lab_id <-> tbl_dating_labs match review -
                                      exploration.ipynb's starting point for
                                      lab_prefix_name_manual_resolution.csv
  a few one-off .xlsx exports from ad-hoc exploration.ipynb cells (mislabeled-study/socken checks)
```

## Scope

The pipeline aims to tackle a problem that, although possible to solve through shapeshifter, would require taking care splitting values and manually resolving certain types of species, which could become a painful task to do through shapeshifter.

This is a faster way as of today for me to implement my knowledge. For example, the process of melting the rows is possible thanks to the Unnest feature in ShapeShifter, but for the process of melting species -> mapping to a manual resolution (requires already to have a mapping dict) -> re-melt, this is a faster path for implementation on my side.

On the journey to resolve this columns, I have tried to reconciliate the data to that of SEAD (for species and materials).  This will be done in ShapeShifter as part of the authority service needed to ensure data quality, but worth having it as there is connections between taxons and common_names to be done in a near future.

## Setup

Same `.env`/`requirements.txt` as the rest of the repo - both live at the true repo root, two
levels above `notebooks/` here. Notebooks are meant to be run from within `current/notebooks/`
(Jupyter's default working directory).
