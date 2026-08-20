# Shared, dataset-agnostic code

Nothing in this folder is tied to a specific Strucke dataset revision.

```
resolution/
  common.py       get_db_engine(), next_available_path(), next_available_dir() - the
                   DB-connection and never-overwrite-a-previous-run helpers. next_available_dir()
                   hands back a fresh per-run output folder (e.g. output/mod_dataset/v1,
                   v1_2, ...) so a run's files can share plain names instead of each carrying
                   its own version/suffix.
  species.py       resolve_species_ids(manual_df, engine) -> (resolved_df, new_records_df).
                   Takes a manual species mapping (manual_species, resolved_order/family/genus/
                   species, common_name_text/language) and resolves it against sead_staging's
                   taxa tables live, proposing new order/family/genus/taxon/common_name records
                   where none already exist. Ported from
                   archive/notebooks/c14_dataset_tranformation.ipynb step 1; used by
                   current/notebooks/c14_v1_dataset_transformation.ipynb.
  material.py      resolve_material_ids(manual_df, engine) -> (resolved_df, new_records_df).
                   Same idea for material -> tbl_abundance_elements/tbl_modification_types.
                   Ported from the same notebook's step 3.
notebooks/
  c14_value_storage_exploration.ipynb   explores where c14_age_bp/c14_error/d13C/pMC_value/
                                         pMC_error/cal_68/cal_95 could live in the sead_staging
                                         schema. Pure schema exploration - never read either raw
                                         dataset file, so it was never tied to v08 or v1.
```

Both `resolve_species_ids` and `resolve_material_ids` take a DataFrame and a live SQLAlchemy
engine, and always recompute ids fresh against the current DB state rather than trusting a
previously-saved CSV - see `current/README.md` for why that matters for the active pipeline.
