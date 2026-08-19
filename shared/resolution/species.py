"""Resolves a manually-completed species mapping (`manual_species` -> resolved_order/family/
genus/species/common_name text) to real sead_staging taxon_id/common_name_id values, proposing
new order/family/genus/taxon/common_name records where SEAD doesn't already have a match.

Ported from `archive/notebooks/c14_dataset_tranformation.ipynb` (step 1), generalized into a
function so both the archive pipeline's historical output and the current v1 pipeline can call it
against a live DB connection instead of trusting a frozen, possibly-stale CSV.
"""

import pandas as pd

REQUIRED_COLUMNS = [
    'manual_species', 'resolved_order', 'resolved_family', 'resolved_genus', 'resolved_species',
    'common_name_text', 'common_name_language',
]

NEW_RECORD_COLUMNS = [
    'table', 'id_column', 'id', 'name', 'language_id', 'author_id', 'parent_table', 'parent_id',
    'created_for',
]


class _SpeciesResolver:
    """Holds the DB-backed lookups plus the in-run proposed-id state for one resolution pass."""

    def __init__(self, engine):
        # LEFT JOIN straight against the public tables (not view_taxa_alphabetically, which
        # silently drops/omits rows it can't fully resolve). taxa_master/common_names_all/
        # sv_common are all derived from this single source so they can't drift out of sync.
        taxa_raw = pd.read_sql(
            """
            select
                m.taxon_id, m.genus_id, m.species, m.author_id,
                g.genus_name, f.family_name, o.order_name,
                c.taxon_common_name_id, c.common_name, c.language_id
            from public.tbl_taxa_tree_master m
            left join public.tbl_taxa_tree_genera g on m.genus_id = g.genus_id
            left join public.tbl_taxa_tree_families f on g.family_id = f.family_id
            left join public.tbl_taxa_tree_orders o on f.order_id = o.order_id
            left join public.tbl_taxa_common_names c on m.taxon_id = c.taxon_id
            """,
            engine,
        )

        self.genera = pd.read_sql(
            'select lower(genus_name) as genus_lc, genus_name, genus_id, family_id '
            'from public.tbl_taxa_tree_genera', engine,
        )
        self.families = pd.read_sql(
            'select lower(family_name) as family_lc, family_name, family_id, order_id '
            'from public.tbl_taxa_tree_families', engine,
        )
        self.orders_lookup = pd.read_sql(
            'select lower(order_name) as order_lc, order_name, order_id '
            'from public.tbl_taxa_tree_orders', engine,
        )

        # One row per taxon_id (author_id kept - SEAD can have several taxon_id rows for the exact
        # same genus+species text, differing only in which taxonomic authority/author_id they're
        # attributed to).
        self.taxa_master = taxa_raw.drop_duplicates('taxon_id')[
            ['taxon_id', 'genus_id', 'species', 'author_id', 'genus_name', 'family_name', 'order_name']
        ].reset_index(drop=True)

        self.common_names_all = (
            taxa_raw.dropna(subset=['taxon_common_name_id'])[
                ['taxon_common_name_id', 'common_name', 'taxon_id', 'language_id']
            ]
            .drop_duplicates()
            .astype({'taxon_common_name_id': 'int64', 'language_id': 'int64'})
            .reset_index(drop=True)
        )

        self.genus_hierarchy = (
            self.genera.merge(self.families[['family_id', 'family_name', 'order_id']], on='family_id', how='left')
                       .merge(self.orders_lookup[['order_id', 'order_name']], on='order_id', how='left')
                       .drop_duplicates('genus_lc').set_index('genus_lc')
        )
        self.family_hierarchy = (
            self.families.merge(self.orders_lookup[['order_id', 'order_name']], on='order_id', how='left')
                         .drop_duplicates('family_lc').set_index('family_lc')
        )
        self.order_hierarchy = self.orders_lookup.drop_duplicates('order_lc').set_index('order_lc')

        self.next_order_id = int(self.orders_lookup['order_id'].max()) + 1
        self.next_family_id = int(self.families['family_id'].max()) + 1
        self.next_genus_id = int(self.genera['genus_id'].max()) + 1
        self.next_taxon_id = int(self.taxa_master['taxon_id'].max()) + 1
        self.next_common_name_id = int(self.common_names_all['taxon_common_name_id'].max()) + 1

        self.proposed_orders = {}         # order_name_lc -> order_id
        self.proposed_families = {}       # family_name_lc -> family_id
        self.proposed_genera = {}         # genus_name_lc -> genus_id
        self.proposed_taxa = {}           # (genus_id, species_lc) -> taxon_id
        self.proposed_common_names = {}   # (taxon_id, language_id, common_name_lc) -> taxon_common_name_id
        self.new_records = []
        self.current_manual_species = None

    def resolve_order(self, order_name):
        """Returns (order_id, is_new)."""
        if order_name is None:
            return None, False
        lc = order_name.lower()
        if lc in self.order_hierarchy.index:
            return int(self.order_hierarchy.loc[lc, 'order_id']), False
        if lc in self.proposed_orders:
            return self.proposed_orders[lc], True
        order_id = self.next_order_id
        self.next_order_id += 1
        self.proposed_orders[lc] = order_id
        self.new_records.append(dict(
            table='tbl_taxa_tree_orders', id_column='order_id', id=order_id, name=order_name,
            language_id=None, author_id=None, parent_table=None, parent_id=None,
            created_for=self.current_manual_species,
        ))
        return order_id, True

    def resolve_family(self, family_name, order_id, order_name_for_placeholder):
        """order_id must already be resolved by the caller. family_name=None -> propose a
        '<order> indet' placeholder family under order_id (or generic 'Indet' if the order itself
        is unknown too). Returns (family_id, is_new, name_used)."""
        if family_name is None:
            family_name = f'{order_name_for_placeholder} indet' if order_name_for_placeholder else 'Indet'
        lc = family_name.lower()
        if lc in self.family_hierarchy.index:
            return int(self.family_hierarchy.loc[lc, 'family_id']), False, family_name
        if lc in self.proposed_families:
            return self.proposed_families[lc], True, family_name
        family_id = self.next_family_id
        self.next_family_id += 1
        self.proposed_families[lc] = family_id
        self.new_records.append(dict(
            table='tbl_taxa_tree_families', id_column='family_id', id=family_id, name=family_name,
            language_id=None, author_id=None, parent_table='tbl_taxa_tree_orders', parent_id=order_id,
            created_for=self.current_manual_species,
        ))
        return family_id, True, family_name

    def resolve_genus(self, genus_name, family_id, family_name_for_placeholder):
        """family_id must already be resolved by the caller. genus_name=None -> propose a
        '<family> indet' placeholder genus under family_id. Returns (genus_id, is_new)."""
        if genus_name is None:
            genus_name = f'{family_name_for_placeholder} indet' if family_name_for_placeholder else 'Indet'
        lc = genus_name.lower()
        if lc in self.genus_hierarchy.index:
            return int(self.genus_hierarchy.loc[lc, 'genus_id']), False
        if lc in self.proposed_genera:
            return self.proposed_genera[lc], True
        genus_id = self.next_genus_id
        self.next_genus_id += 1
        self.proposed_genera[lc] = genus_id
        self.new_records.append(dict(
            table='tbl_taxa_tree_genera', id_column='genus_id', id=genus_id, name=genus_name,
            language_id=None, author_id=None, parent_table='tbl_taxa_tree_families', parent_id=family_id,
            created_for=self.current_manual_species,
        ))
        return genus_id, True

    def resolve_taxon(self, genus_id, species_epithet):
        """species_epithet=None means we only know the genus - look for/propose that genus's
        indeterminate-species placeholder (SEAD uses both 'indet.' and 'sp.' for this - check
        both). Only an existing taxon with author_id IS NULL is safe to reuse outright.
        Returns (taxon_id, is_new, blocked_by_author_id)."""
        target_lc = (species_epithet or 'indet.').lower().rstrip('.')
        genus_taxa = self.taxa_master[self.taxa_master['genus_id'] == genus_id]

        if species_epithet is not None:
            candidates = genus_taxa[genus_taxa['species'].str.lower().str.rstrip('.') == target_lc]
        else:
            candidates = genus_taxa[
                (genus_taxa['species'].str.lower().str.rstrip('.') == target_lc)
                | genus_taxa['species'].str.lower().str.startswith(('indet', 'sp.', 'spp.'))
            ]

        usable = candidates[candidates['author_id'].isna()]
        blocked_by_author_id = len(candidates) > 0 and usable.empty

        if len(usable):
            return int(usable.iloc[0]['taxon_id']), False, blocked_by_author_id

        key = (genus_id, target_lc)
        species_text = species_epithet or 'indet.'
        if key in self.proposed_taxa:
            return self.proposed_taxa[key], True, blocked_by_author_id
        taxon_id = self.next_taxon_id
        self.next_taxon_id += 1
        self.proposed_taxa[key] = taxon_id
        self.new_records.append(dict(
            table='tbl_taxa_tree_master', id_column='taxon_id', id=taxon_id, name=species_text,
            language_id=None, author_id=None, parent_table='tbl_taxa_tree_genera', parent_id=genus_id,
            created_for=self.current_manual_species,
        ))
        return taxon_id, True, blocked_by_author_id

    def resolve_common_name(self, taxon_id, common_name_text, language_id, taxon_is_new):
        common_name_lc = common_name_text.rstrip('?').strip().lower()
        if not taxon_is_new:
            existing = self.common_names_all[
                (self.common_names_all['taxon_id'] == taxon_id)
                & (self.common_names_all['language_id'] == language_id)
            ]
            if len(existing):
                return int(existing.iloc[0]['taxon_common_name_id']), False
        key = (taxon_id, language_id, common_name_lc)
        if key in self.proposed_common_names:
            return self.proposed_common_names[key], True
        common_name_id = self.next_common_name_id
        self.next_common_name_id += 1
        self.proposed_common_names[key] = common_name_id
        self.new_records.append(dict(
            table='tbl_taxa_common_names', id_column='taxon_common_name_id', id=common_name_id,
            name=common_name_text, language_id=language_id, author_id=None,
            parent_table='tbl_taxa_tree_master', parent_id=taxon_id, created_for=self.current_manual_species,
        ))
        return common_name_id, True

    def resolve_row(self, row):
        self.current_manual_species = row['manual_species']

        order = row['resolved_order'] if pd.notna(row['resolved_order']) else None
        family = row['resolved_family'] if pd.notna(row['resolved_family']) else None
        genus = row['resolved_genus'] if pd.notna(row['resolved_genus']) else None
        species_epithet = row['resolved_species'] if pd.notna(row['resolved_species']) else None

        order_id, order_is_new = None, False
        family_id, family_is_new = None, False
        genus_id, genus_is_new = None, False
        taxon_id, taxon_is_new, blocked_by_author_id = None, False, False

        if order or family or genus:
            order_id, order_is_new = self.resolve_order(order)
            family_id, family_is_new, family_name_used = self.resolve_family(family, order_id, order)
            genus_id, genus_is_new = self.resolve_genus(genus, family_id, family_name_used)
            taxon_id, taxon_is_new, blocked_by_author_id = self.resolve_taxon(genus_id, species_epithet)

        common_name_id, common_name_is_new = None, False
        common_name_text = row['common_name_text'] if pd.notna(row['common_name_text']) else None
        common_name_language = row['common_name_language'] if pd.notna(row['common_name_language']) else None
        if taxon_id is not None and common_name_text is not None and common_name_language is not None:
            common_name_id, common_name_is_new = self.resolve_common_name(
                taxon_id, common_name_text, int(common_name_language), taxon_is_new
            )

        return pd.Series(dict(
            resolved_order_id=order_id, resolved_order_is_new=bool(order_is_new),
            resolved_family_id=family_id, resolved_family_is_new=bool(family_is_new),
            resolved_genus_id=genus_id, resolved_genus_is_new=bool(genus_is_new),
            taxon_id=taxon_id, taxon_id_is_new=bool(taxon_is_new),
            matched_existing_taxon=(taxon_id is not None and not taxon_is_new),
            blocked_by_existing_author_id=bool(blocked_by_author_id),
            common_name_id=common_name_id, common_name_id_is_new=bool(common_name_is_new),
        ))


def resolve_species_ids(manual_df, engine):
    """manual_df must contain REQUIRED_COLUMNS (extra columns pass through untouched, and must
    NOT already contain any of the resolved_*_id/is_new/taxon_id/common_name_id columns this
    function computes - passing in a draft that already has them was the source of a duplicate-
    column bug in the old notebook pipeline).

    Returns (resolved_df, new_sead_records_df): resolved_df is manual_df with resolved_order_id,
    resolved_order_is_new, resolved_family_id, resolved_family_is_new, resolved_genus_id,
    resolved_genus_is_new, taxon_id, taxon_id_is_new, matched_existing_taxon,
    blocked_by_existing_author_id, common_name_id, common_name_id_is_new appended; new_sead_records_df
    lists every fabricated order/family/genus/taxon/common_name row proposed along the way.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in manual_df.columns]
    if missing:
        raise ValueError(f'manual_df is missing required columns: {missing}')

    resolver = _SpeciesResolver(engine)
    resolution = manual_df.apply(resolver.resolve_row, axis=1)
    resolved_df = pd.concat([manual_df.reset_index(drop=True), resolution], axis=1)

    new_records_df = pd.DataFrame(resolver.new_records, columns=NEW_RECORD_COLUMNS)
    return resolved_df, new_records_df
