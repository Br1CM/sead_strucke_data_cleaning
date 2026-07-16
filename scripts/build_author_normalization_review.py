"""Rebuilds output/author_normalization_review.csv from data/c14_master_v08.xlsx.

Parses every unique raw `author` value with a heuristic normalizer targeting the
`Surname, N., Surname2, N2. & Surname3, N3.` pattern, flagging anything it can't
confidently reorder rather than guessing. Extracted from explore.ipynb.
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EXCEL_PATH = ROOT / "data" / "c14_master_v08.xlsx"
OUTPUT_PATH = ROOT / "output" / "author_normalization_review.csv"

ET_AL_RE = re.compile(r'[,\s]*\(?\bm\.?\s*f\.?l\.?\)?\.?\s*$', re.I)
RED_RE = re.compile(r'[,\s]*\(?\s*red\.?\s*\)?\.?\s*$', re.I)
PARTICLE_RE = re.compile(r'\b(von|van|af|de)\b', re.I)
DIGIT_RE = re.compile(r'\d')
OCH_RE = re.compile(r'\s+och\s+', re.I)
NAME_WORD = r"[A-ZÅÄÖÜ][\wÀ-ÿ\-']*"
# "Surname. Firstname" \ "Surname; Firstname" \ "Surname: Firstname" (typo'd comma)
PSEUDO_COMMA_RE = re.compile(rf'^({NAME_WORD})[.;:]\s+({NAME_WORD})$')
# "Surname Initial" with no separator at all, e.g. "Ebbesen K" / "Adamsen Chr."
SHORT_INITIAL_RE = re.compile(rf'^({NAME_WORD})\s+([A-ZÅÄÖÜ][a-zåäöA-ZÅÄÖ]{{0,3}}\.?)$')
PARTICLE_WORDS = {'von', 'van', 'af', 'de', 'der', 'den', 'zu', 'du', 'la', 'le'}


def strip_suffixes(s):
    """Pull off trailing 'm fl' (et al.) / '(red)' (ed.) annotations, in either order."""
    et_al = False
    editor = False
    changed = True
    while changed:
        changed = False
        new_s = ET_AL_RE.sub('', s)
        if new_s != s:
            et_al, s, changed = True, new_s, True
        new_s = RED_RE.sub('', s)
        if new_s != s:
            editor, s, changed = True, new_s, True
    return s.strip(' ,.'), et_al, editor


def fix_particle_order(surname, firstname):
    """Move a trailing nobility particle (e.g. 'Magnus von der') from the firstname
    back onto the surname ('von der Luft'), which is where OCR/data-entry usually lost it."""
    words = firstname.split()
    particles = []
    while words and words[-1].lower() in PARTICLE_WORDS:
        particles.insert(0, words.pop().lower())
    if particles:
        surname = ' '.join(particles) + ' ' + surname
        firstname = ' '.join(words)
    return surname, firstname


def initialize(name_part):
    """Turn a first-name segment into an initial, e.g. 'Mattias' -> 'M.', 'Anna-Karin' -> 'A.'"""
    name_part = name_part.strip(' .')
    if not name_part:
        return ''
    first_word = re.split(r'[\s\-]', name_part)[0]
    return first_word[0].upper() + '.' if first_word else ''


def parse_no_comma_segment(segment):
    """Try to safely split a single no-comma author segment into (surname, firstname).
    Returns None if the order can't be determined with confidence."""
    segment = segment.strip()
    m = PSEUDO_COMMA_RE.match(segment) or SHORT_INITIAL_RE.match(segment)
    return (m.group(1), m.group(2)) if m else None


def build_result(original, formatted, et_al, editor, flags):
    suffix = ''
    if et_al:
        suffix += ' et al.'
    if editor:
        suffix += ' (ed.)'
    formatted_full = (formatted + suffix).strip()
    needs_review = 'needs_review' in flags
    reason = ','.join(sorted(set(f for f in flags if f != 'needs_review')))
    return original, formatted_full, needs_review, reason


def parse_author_string(raw):
    original = raw
    flags = []

    s = OCH_RE.sub(' & ', raw.strip())
    s, et_al, editor = strip_suffixes(s)
    if et_al:
        flags.append('et_al')
    if editor:
        flags.append('editor')
    if DIGIT_RE.search(s):
        flags.append('digits')
    if PARTICLE_RE.search(s):
        flags.append('particle')

    if ',' not in s:
        flags.append('no_comma')
        segments = [seg.strip() for seg in re.split(r'\s*&\s*', s) if seg.strip()]
        parsed_pairs = [parse_no_comma_segment(seg) for seg in segments]
        if all(parsed_pairs):
            authors = [f'{surname}, {initialize(firstname)}'.strip() for surname, firstname in parsed_pairs]
            formatted = authors[0] if len(authors) == 1 else ', '.join(authors[:-1]) + ' & ' + authors[-1]
        else:
            formatted = s  # can't safely determine name order
            flags.append('needs_review')
        return build_result(original, formatted, et_al, editor, flags)

    # a single '&' always precedes the final author in this dataset (verified: no multi-'&' cases)
    s_norm = re.sub(r'\s*&\s*', ', ', s)
    tokens = [t.strip() for t in s_norm.split(',') if t.strip()]

    if len(tokens) % 2 != 0:
        # repair pass: the last token may itself hide an unseparated "Surname Initial" pair
        m = SHORT_INITIAL_RE.match(tokens[-1]) if tokens else None
        if m:
            tokens = tokens[:-1] + [m.group(1), m.group(2)]

    if len(tokens) % 2 != 0:
        flags += ['odd_tokens', 'needs_review']
        return build_result(original, s, et_al, editor, flags)

    authors = []
    for i in range(0, len(tokens), 2):
        surname, firstname = tokens[i], tokens[i + 1]
        if 'particle' in flags:
            surname, firstname = fix_particle_order(surname, firstname)
        initial = initialize(firstname)
        if not initial:
            flags.append('needs_review')
        authors.append(f'{surname}, {initial}'.strip())

    formatted = authors[0] if len(authors) == 1 else ', '.join(authors[:-1]) + ' & ' + authors[-1]
    if 'digits' in flags:
        flags.append('needs_review')

    return build_result(original, formatted, et_al, editor, flags)


df = pd.read_excel(EXCEL_PATH)
unique_authors = sorted(df['author'].dropna().unique())

rows = []
for a in unique_authors:
    original, formatted, needs_review, reason = parse_author_string(a)
    rows.append({'author_raw': original, 'author_parsed': formatted, 'needs_review': needs_review, 'flag_reason': reason})

author_review_df = pd.DataFrame(rows)
author_review_df.to_csv(OUTPUT_PATH, index=False, encoding='utf-8-sig')

total = len(author_review_df)
flagged = author_review_df['needs_review'].sum()
print(f'total unique authors: {total}')
print(f'flagged for review: {flagged} ({flagged/total:.1%})')
print()
print(author_review_df.loc[author_review_df['needs_review'], 'flag_reason'].value_counts())
