"""Resolves a manually-completed material breakdown (`material` -> up to 3 sead_element_N names +
an optional sead_modification_type, all under a real sead_record_type_id) to real sead_staging
tbl_abundance_elements/tbl_modification_types ids, proposing new element/modification records
where SEAD doesn't already have a match.

Ported from `archive/notebooks/c14_dataset_tranformation.ipynb` (step 3), generalized into a
function so both the archive pipeline's historical output and the current v1 pipeline can call it
against a live DB connection instead of trusting a frozen, possibly-stale CSV.
"""

import pandas as pd

REQUIRED_COLUMNS = [
    'sead_element_1', 'sead_element_2', 'sead_element_3', 'sead_modification_type',
    'sead_record_type_id',
]

NEW_RECORD_COLUMNS = ['table', 'id_column', 'id', 'name', 'record_type_id']

# SEAD already has 'Seed grain' (record_type_id=2) - same concept as the manually-assigned
# 'Seed', so reuse it instead of proposing a duplicate new element. Keyed on (record_type_id,
# element_name_lc) so this only fires for that specific record type.
ELEMENT_ALIASES = {
    (2, 'seed'): 'Seed grain',
}


def resolve_material_ids(manual_df, engine):
    """manual_df must contain REQUIRED_COLUMNS (extra columns, e.g. `material`, pass through
    untouched).

    Returns (resolved_df, new_sead_records_df): resolved_df is manual_df with
    sead_element_{1,2,3}_id, sead_element_{1,2,3}_is_new, sead_modification_type_id,
    modification_type_is_new appended; new_sead_records_df lists every fabricated
    abundance-element/modification-type row proposed along the way.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in manual_df.columns]
    if missing:
        raise ValueError(f'manual_df is missing required columns: {missing}')

    manual_df = manual_df.copy()
    for col in ['sead_element_1', 'sead_element_2', 'sead_element_3']:
        for (record_type_id, name_lc), alias in ELEMENT_ALIASES.items():
            is_alias = (
                manual_df[col].notna()
                & (manual_df[col].str.strip().str.lower() == name_lc)
                & (manual_df['sead_record_type_id'] == record_type_id)
            )
            manual_df.loc[is_alias, col] = alias

    abundance_elements = pd.read_sql(
        'select abundance_element_id, record_type_id, element_name from public.tbl_abundance_elements', engine
    )
    abundance_elements['element_name_lc'] = abundance_elements['element_name'].str.lower()
    existing_element_lookup = abundance_elements.set_index(
        ['record_type_id', 'element_name_lc']
    )['abundance_element_id'].to_dict()

    modification_types = pd.read_sql(
        'select modification_type_id, modification_type_name from public.tbl_modification_types', engine
    )
    modification_types['name_lc'] = modification_types['modification_type_name'].str.lower()
    modification_lookup = modification_types.set_index('name_lc')['modification_type_id'].to_dict()

    next_element_id = int(abundance_elements['abundance_element_id'].max()) + 1
    next_modification_id = int(modification_types['modification_type_id'].max()) + 1

    proposed_elements = {}       # (record_type_id, element_name_lc) -> abundance_element_id
    proposed_modifications = {}  # modification_name_lc -> modification_type_id
    new_records = []

    def resolve_element(element_name, record_type_id):
        nonlocal next_element_id
        if pd.isna(element_name):
            return None, False
        name_lc = str(element_name).strip().lower()
        key = (int(record_type_id), name_lc)
        if key in existing_element_lookup:
            return int(existing_element_lookup[key]), False
        if key in proposed_elements:
            return proposed_elements[key], True
        new_id = next_element_id
        next_element_id += 1
        proposed_elements[key] = new_id
        new_records.append(dict(
            table='tbl_abundance_elements', id_column='abundance_element_id', id=new_id,
            name=element_name, record_type_id=int(record_type_id),
        ))
        return new_id, True

    def resolve_modification(modification_name):
        nonlocal next_modification_id
        if pd.isna(modification_name):
            return None, False
        name_lc = str(modification_name).strip().lower()
        if name_lc in modification_lookup:
            return int(modification_lookup[name_lc]), False
        if name_lc in proposed_modifications:
            return proposed_modifications[name_lc], True
        new_id = next_modification_id
        next_modification_id += 1
        proposed_modifications[name_lc] = new_id
        new_records.append(dict(
            table='tbl_modification_types', id_column='modification_type_id', id=new_id,
            name=modification_name, record_type_id=None,
        ))
        return new_id, True

    resolved_df = manual_df.reset_index(drop=True)
    for i in (1, 2, 3):
        col = f'sead_element_{i}'
        resolved = resolved_df.apply(
            lambda row: pd.Series(resolve_element(row[col], row['sead_record_type_id']),
                                   index=[f'{col}_id', f'{col}_is_new']),
            axis=1,
        )
        resolved_df = pd.concat([resolved_df, resolved], axis=1)

    mod_resolved = resolved_df['sead_modification_type'].apply(
        lambda v: pd.Series(resolve_modification(v), index=['sead_modification_type_id', 'modification_type_is_new'])
    )
    resolved_df = pd.concat([resolved_df, mod_resolved], axis=1)

    new_records_df = pd.DataFrame(new_records, columns=NEW_RECORD_COLUMNS)
    return resolved_df, new_records_df
