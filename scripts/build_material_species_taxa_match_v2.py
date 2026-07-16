"""Rebuilds output/species_taxa_token_matches.csv, output/material_species_taxa_matches.csv,
and output/material_species_taxa_match_v2.csv from data/c14_master_v08.xlsx and the
sead_staging taxa tables.

Extracts every distinct (material, species) pair from the source data, splits each species
value into tokens, matches each token against the sead_staging taxonomic hierarchy (species
common name -> genus -> family -> order, with a suffix-inference fallback for Swedish
compound tree names), then re-attaches results to the original rows and to the exact SEAD
common name / species binomial. Extracted from explore.ipynb and material_species_taxa_matching.ipynb.
"""
import os
import re
from collections import Counter
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = ROOT / "data" / "c14_master_v08.xlsx"
TOKEN_MATCHES_PATH = ROOT / "output" / "species_taxa_token_matches.csv"
MATCHES_PATH = ROOT / "output" / "material_species_taxa_matches.csv"
MATCHES_V2_PATH = ROOT / "output" / "material_species_taxa_match_v2.csv"

load_dotenv(ROOT / ".env")

DB_HOST = os.environ["DB_HOST"]
DB_PORT = os.environ["DB_PORT"]
DB_NAME = os.environ["DB_NAME"]
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]

engine = create_engine(f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}")

SPLIT_RE = re.compile(r'\s*(?:,|/|\bresp\.?\b|\bsamt\b|\boch\b|&)\s*', re.I)


def tokenize(species_value):
    return [p.strip(' ?.') for p in SPLIT_RE.split(species_value) if p.strip(' ?.')]


LATIN_QUALIFIER_RE = re.compile(r'^(cf\.?\s+|aff\.?\s+)|(\s+(sp\.?|spp\.?|indet\.?)\s*$)', re.I)


def strip_latin_qualifiers(token):
    prev = None
    while prev != token:
        prev = token
        token = LATIN_QUALIFIER_RE.sub('', token).strip()
    return token


def match_exact(token_lc):
    if token_lc in common_map.index:
        rec = common_map.loc[token_lc]
        return dict(match_level='species (common name)', genus=rec['genus'], family=rec['family'], order=rec['order'],
                    detail=f"{rec['genus']} {rec['species']}")
    cleaned = strip_latin_qualifiers(token_lc)
    if cleaned in genus_hierarchy.index:
        rec = genus_hierarchy.loc[cleaned]
        return dict(match_level='genus (latin)', genus=rec['genus_name'], family=rec['family_name'], order=rec['order_name'],
                    detail=rec['genus_name'])
    if cleaned in family_hierarchy.index:
        rec = family_hierarchy.loc[cleaned]
        return dict(match_level='family (latin)', genus=None, family=rec['family_name'], order=rec['order_name'],
                    detail=rec['family_name'])
    if cleaned in order_hierarchy.index:
        rec = order_hierarchy.loc[cleaned]
        return dict(match_level='order (latin)', genus=None, family=None, order=rec['order_name'], detail=rec['order_name'])
    return None


def infer_genus_by_suffix(token_lc):
    """Swedish tree names compound as <modifier><base>, e.g. 'klibbal' -> Alnus. Only
    accepted when every common name ending in the token converges on a single genus."""
    if len(token_lc) < 2 or not token_lc.isalpha():
        return None
    hits = sv_common[sv_common['common_name_lc'].str.endswith(token_lc)]
    if hits.empty:
        return None
    candidate_genera = hits['genus'].unique().tolist()
    if len(candidate_genera) == 1:
        rec = genus_hierarchy[genus_hierarchy['genus_name'] == candidate_genera[0]]
        return dict(match_level='genus (suffix-inferred)', genus=candidate_genera[0],
                    family=rec['family_name'].iloc[0] if len(rec) else None,
                    order=rec['order_name'].iloc[0] if len(rec) else None,
                    detail=f'{len(hits)} common names -> {candidate_genera[0]}', needs_review=False)
    return dict(match_level='genus (suffix, ambiguous)', genus=None, family=None, order=None,
                detail=f"candidates: {', '.join(candidate_genera[:6])}", needs_review=True)


def summarize_species_value(species_value):
    toks = tokenize(species_value)
    if not toks:
        return pd.Series({'n_tokens': 0, 'n_matched': 0, 'best_match_level': None,
                           'matched_genera': None, 'matched_families': None, 'matched_orders': None})
    levels, genera_hit, fam_hit, ord_hit, matched = [], set(), set(), set(), 0
    for t in toks:
        info = token_lookup.loc[t] if t in token_lookup.index else None
        if info is not None and pd.notna(info['match_level']) and LEVEL_RANK.get(info['match_level'], -1) > 0:
            matched += 1
            levels.append(info['match_level'])
            if pd.notna(info['genus']):
                genera_hit.add(info['genus'])
            if pd.notna(info['family']):
                fam_hit.add(info['family'])
            if pd.notna(info['order']):
                ord_hit.add(info['order'])
    best = max(levels, key=lambda l: LEVEL_RANK.get(l, -1)) if levels else None
    return pd.Series({
        'n_tokens': len(toks), 'n_matched': matched, 'best_match_level': best,
        'matched_genera': ', '.join(sorted(genera_hit)) or None,
        'matched_families': ', '.join(sorted(fam_hit)) or None,
        'matched_orders': ', '.join(sorted(ord_hit)) or None,
    })


def sead_species_lookup(token):
    token_lc = token.lower()
    if token_lc in common_map.index:
        rec = common_map.loc[token_lc]
        return rec['common_name'], f"{rec['genus']} {rec['species']}"
    return None, None


def summarize_species_value_v2(species_value):
    toks = tokenize(species_value)
    if not toks:
        return pd.Series({'sead_common_name': None, 'sead_species_name': None})
    common_names_hit, species_names_hit = [], []
    for t in toks:
        info = token_lookup_v2.loc[t] if t in token_lookup_v2.index else None
        if info is None:
            continue
        if pd.notna(info['sead_common_name']) and info['sead_common_name'] not in common_names_hit:
            common_names_hit.append(info['sead_common_name'])
        if pd.notna(info['sead_species_name']) and info['sead_species_name'] not in species_names_hit:
            species_names_hit.append(info['sead_species_name'])
    return pd.Series({
        'sead_common_name': '; '.join(common_names_hit) or None,
        'sead_species_name': '; '.join(species_names_hit) or None,
    })


df = pd.read_excel(INPUT_PATH)
material_species = (
    df[['material', 'species']]
    .value_counts(dropna=False)
    .reset_index(name='n_rows')
    .sort_values(['material', 'species'], na_position='first')
    .reset_index(drop=True)
)

sv_common = pd.read_sql("""
    select lower(cn.common_name) as common_name_lc, cn.common_name,
           v.taxon_id, v.species, v.genus, v.family, v."order"
    from public.tbl_taxa_common_names cn
    join public.view_taxa_alphabetically v on v.taxon_id = cn.taxon_id
    where cn.language_id = 2
""", engine)
genera = pd.read_sql('select lower(genus_name) as genus_lc, genus_name, genus_id, family_id from public.tbl_taxa_tree_genera', engine)
families = pd.read_sql('select lower(family_name) as family_lc, family_name, family_id, order_id from public.tbl_taxa_tree_families', engine)
orders_lookup = pd.read_sql('select lower(order_name) as order_lc, order_name, order_id from public.tbl_taxa_tree_orders', engine)

common_map = sv_common.drop_duplicates('common_name_lc').set_index('common_name_lc')
genus_hierarchy = (
    genera.merge(families[['family_id', 'family_name', 'order_id']], on='family_id', how='left')
          .merge(orders_lookup[['order_id', 'order_name']], on='order_id', how='left')
          .drop_duplicates('genus_lc').set_index('genus_lc')
)
family_hierarchy = (
    families.merge(orders_lookup[['order_id', 'order_name']], on='order_id', how='left')
             .drop_duplicates('family_lc').set_index('family_lc')
)
order_hierarchy = orders_lookup.drop_duplicates('order_lc').set_index('order_lc')

token_counts = Counter()
for species_value, n in material_species.dropna(subset=['species'])[['species', 'n_rows']].itertuples(index=False):
    for tok in tokenize(species_value):
        token_counts[tok] += n

rows = []
for token, n in token_counts.items():
    token_lc = token.lower()
    result = match_exact(token_lc) or infer_genus_by_suffix(token_lc) or dict(match_level=None, genus=None, family=None, order=None, detail=None)
    result.setdefault('needs_review', result['match_level'] is None)
    result['token'] = token
    result['n_rows'] = n
    rows.append(result)

token_matches = pd.DataFrame(rows)[['token', 'n_rows', 'match_level', 'genus', 'family', 'order', 'detail', 'needs_review']]
token_matches = token_matches.sort_values('n_rows', ascending=False).reset_index(drop=True)

token_lookup = token_matches.set_index('token')[['match_level', 'genus', 'family', 'order']]
LEVEL_RANK = {
    'species (common name)': 4, 'genus (latin)': 3, 'genus (suffix-inferred)': 3,
    'family (latin)': 2, 'order (latin)': 1, 'genus (suffix, ambiguous)': 0,
}

match_summary = material_species['species'].fillna('').apply(summarize_species_value)
material_species_matched = pd.concat([material_species, match_summary], axis=1)

token_matches.to_csv(TOKEN_MATCHES_PATH, index=False, encoding='utf-8-sig')
material_species_matched.to_csv(MATCHES_PATH, index=False, encoding='utf-8-sig')

tagged = material_species_matched[material_species_matched['species'].notna()]
total_rows = tagged['n_rows'].sum()
covered_rows = tagged.loc[tagged['n_matched'] > 0, 'n_rows'].sum()
fully_covered_rows = tagged.loc[tagged['n_matched'] == tagged['n_tokens'], 'n_rows'].sum()

print(f'rows with a species value tagged:    {total_rows:,}')
print(f'rows with >=1 taxon token resolved:  {covered_rows:,} ({covered_rows/total_rows:.1%})')
print(f'rows with ALL taxon tokens resolved: {fully_covered_rows:,} ({fully_covered_rows/total_rows:.1%})')

# v2: attach the exact SEAD common name and species binomial where matched at species level
token_matches[['sead_common_name', 'sead_species_name']] = token_matches['token'].apply(
    lambda t: pd.Series(sead_species_lookup(t))
)

token_lookup_v2 = token_matches.set_index('token')[
    ['match_level', 'genus', 'family', 'order', 'sead_common_name', 'sead_species_name']
]

sead_fields = material_species['species'].fillna('').apply(summarize_species_value_v2)
material_species_matched_v2 = pd.concat([material_species_matched, sead_fields], axis=1)

print(f"rows with sead_species_name populated: {material_species_matched_v2['sead_species_name'].notna().sum()} / {len(material_species_matched_v2)}")

material_species_matched_v2.to_csv(MATCHES_V2_PATH, index=False, encoding='utf-8-sig')
