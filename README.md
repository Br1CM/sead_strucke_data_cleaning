# SEAD Strucke Data Cleaning

Exploratory and transformation work on the Strucke radiocarbon-dating dataset ahead of its
ingestion into the [SEAD](https://www.sead.se/) database. The goal is to understand the shape and
quality of the dataset, tie its values back to what already exists in the `sead_staging` database
(taxonomy, materials, dating methods, sites, authors), and produce a fully "tidy" long-format
export - one row per fact - ready for ingestion.

A second revision of the raw dataset (`StruckeC14_Sweden_v1.csv`) superseded the original
(`c14_master_v08.xlsx`), so the repo is split into three spaces:

- **[`current/`](current/)** - the active pipeline, targeting `StruckeC14_Sweden_v1.csv`.
  Self-contained: it never reads from `archive/` or from its own `output/` at runtime. Start here.
- **[`archive/`](archive/)** - the complete, frozen v08 pipeline, preserved for reference. Not
  maintained going forward, but fully reproducible from a clean checkout if you need to go back to it.
- **[`shared/`](shared/)** - dataset-agnostic code and notebooks used by (or usable by) both:
  the SEAD id-resolution functions `current/`'s pipeline calls live, plus a DB-schema-exploration
  notebook that was never tied to either raw file.

Each has its own README with the detail specific to that space.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in your sead_staging DB credentials
```

`.env` and `requirements.txt` are shared by every space and live here at the repo root. Notebooks
are meant to be run from within their own `notebooks/` folder (Jupyter's default working
directory) - see `current/README.md` / `archive/README.md` for the exact relative paths that
implies.
