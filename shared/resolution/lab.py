"""Resolves a `lab_id`-style column's *prefix* (the letters before the dash/number, e.g. `Ua` in
`Ua-49252`) against a manually-completed prefix/name mapping to attach standardized
`lab_prefix`/`lab_name` columns.

`lab_id_prefix()` is the same three-way categorization (`standard`/`unknown_no_lab`/
`non_standard_id`) used in `current/notebooks/exploration.ipynb` to match against SEAD's
`tbl_dating_labs`; that notebook's `lab_id_prefix_matches.csv` export is the starting point for
the hand-completed `data/manual_resolutions/lab_prefix_name_manual_resolution.csv` this module
reads.
"""

import re

REQUIRED_COLUMNS = ['lab_id_prefix', 'lab_id_prefix_category', 'manual_prefix', 'manual_lab_name']


def lab_id_prefix(lab_id):
    """Splits a `lab_id`-style value into (prefix, category); category is one of `standard`,
    `unknown_no_lab`, `non_standard_id`. Ported from `current/notebooks/exploration.ipynb`."""
    s = str(lab_id)
    # "Okänd<number>" means the *sample number* is unknown, not the lab -- drop it before
    # reading the prefix, e.g. "Ua-Okänd62" -> "Ua"
    core = re.sub(r"[-\s]?[Oo]k[äa]nd\s*\d*", "", s)
    leading = re.match(r"^[A-Za-z]+", core)
    if leading:
        return leading.group(0), "standard"
    if core.strip() == "":
        return "(Okänd -- no lab given at all)", "unknown_no_lab"
    # no leading letter, but there might be one buried in there (e.g. the "C" in "17C/0902")
    embedded = re.search(r"[A-Za-z]+", core)
    tag = embedded.group(0) if embedded else "?"
    return f"~{tag} (embedded, not a leading prefix)", "non_standard_id"


def resolve_lab_prefix_name(df, manual_df, lab_id_col='lab_id'):
    """df must contain `lab_id_col`. manual_df must contain REQUIRED_COLUMNS, one row per
    unique (lab_id_prefix, lab_id_prefix_category) pair -- the hand-reviewed output of
    `lab_id_prefix_matches.csv`.

    Returns df with `lab_id_prefix`/`lab_id_prefix_category` (derived from `lab_id_col`) and
    `lab_prefix`/`lab_name` (from manual_df's manual_prefix/manual_lab_name) appended. Raises if
    any row's (prefix, category) has no match in manual_df, since that means a `lab_id_col` shape
    has shown up that the manual file hasn't been reviewed against yet.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in manual_df.columns]
    if missing:
        raise ValueError(f'manual_df is missing required columns: {missing}')

    df = df.copy()
    parsed = df[lab_id_col].apply(lab_id_prefix)
    df['lab_id_prefix'] = parsed.apply(lambda t: t[0])
    df['lab_id_prefix_category'] = parsed.apply(lambda t: t[1])

    mapping = manual_df[REQUIRED_COLUMNS].rename(
        columns={'manual_prefix': 'lab_prefix', 'manual_lab_name': 'lab_name'}
    )
    resolved = df.merge(mapping, on=['lab_id_prefix', 'lab_id_prefix_category'], how='left')

    unresolved = resolved.loc[resolved['lab_prefix'].isna(), ['lab_id_prefix', 'lab_id_prefix_category']]
    if not unresolved.empty:
        missing_pairs = unresolved.drop_duplicates().to_dict('records')
        raise ValueError(
            f'{len(unresolved)} rows have no match in the manual lab prefix/name mapping: {missing_pairs}'
        )

    return resolved
