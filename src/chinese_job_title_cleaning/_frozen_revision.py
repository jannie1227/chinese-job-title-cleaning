#!/usr/bin/env python3
"""Apply frozen v1.2.12 revisions to a v1.2.11 sealed-format CSV.

This entry point deliberately does not claim raw-to-final metadata reproduction.
Private unresolved-combination rules may be supplied locally with --pending-rules.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
from ._revision import revision_v1212 as rule

BASELINE_SHA256 = 'a6edbed01982b14658d98da8c23684a2ba09c878b11d258652e1253d38dc16a3'
HEADERS = ['record_id', '招聘发布年份', '招聘岗位_raw', 'clean_title', 'match_title_core', 'soc_route_precheck', 'multi_occupation_candidates', 'title_cleaning_method', 'title_attention', '招聘类别_raw', '招聘类别_clean', '招聘类别_route_type', '招聘类别_occupation_category_hint', '招聘类别_source_industry_hint', '招聘类别_unparsed_text', '初级分类_raw', '初级分类_clean', '初级分类_route_type', '初级分类_occupation_category_hint', '初级分类_source_industry_hint', '初级分类_unparsed_text', 'employment_type_clean', 'recruitment_channel_clean', 'occupation_category_hint', 'source_industry_hint', 'category_use_status', 'occupation_hint_soc_use', 'category_issue', '上市公司行业_raw', '上市公司行业_clean', 'ruleset_version']
KEY_IX = (3, 4, 10, 16, 29, 21, 22, 23, 24, 25, 26, 27, 5, 6)
KEY_NAMES = ['clean_title', 'match_title_core', '招聘类别_clean', '初级分类_clean', '上市公司行业_clean', 'employment_type_clean', 'recruitment_channel_clean', 'occupation_category_hint', 'source_industry_hint', 'category_use_status', 'occupation_hint_soc_use', 'category_issue', 'soc_route_precheck', 'multi_occupation_candidates', 'soc_input_route', 'occupation_hint_auxiliary', 'occupation_hint_candidates_only', 'known_pending_issue']
EXTRA = ['final_match_item_id', 'soc_input_route', 'occupation_hint_auxiliary', 'occupation_hint_candidates_only', 'known_pending_issue', 'ruleset_hash']
BRIDGE = ['record_id', 'final_match_item_id', 'soc_input_route', 'ruleset_version', 'ruleset_hash']
PROTECTED = (0, 1, 2, 9, 15, 28, 29)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def file_sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def routing(a, flag):
    if a[5] == 'X':
        route = 'NO_OCCUPATION'
    elif a[5] == 'C':
        route = 'MULTI_OCCUPATION'
    elif flag or not a[4] or a[5] != 'SINGLE':
        route = 'REVIEW_REQUIRED'
    else:
        route = 'CANDIDATE_READY'
    aux = a[23] if a[25] == 'usable' and a[26] == 'auxiliary' else ''
    broad = a[23] if a[25] == 'weak' and a[26] == 'candidate_expansion_only' else ''
    if a[25] in {'conflict', 'malformed'} and (aux or broad):
        raise ValueError('Disabled category evidence became usable.')
    return [route, aux, broad, flag]


def item_key(a, flag):
    return canonical([a[i] for i in KEY_IX] + routing(a, flag))


def item_id(key):
    return 'MI1212_' + hashlib.sha256(key.encode('utf-8')).hexdigest()


@contextmanager
def csv_output(path, headers):
    with Path(path).open('wb') as binary:
        with gzip.GzipFile(filename='', fileobj=binary, mode='wb', mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding='utf-8-sig', newline='') as text:
                writer = csv.writer(text, lineterminator='\n')
                writer.writerow(headers)
                yield writer


def load_pending(path):
    if path is None:
        return {}
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Pending rules must be an object mapping canonical four-field arrays to flags.')
    for key, value in data.items():
        fields = json.loads(key)
        if not isinstance(fields, list) or len(fields) != 4 or not all(isinstance(x, str) for x in fields) or key != canonical(fields) or value != 'AI_KNOWN_UNRESOLVED':
            raise ValueError('Invalid pending-rule schema.')
    return data


def run(input_path, output_dir, pending_path=None):
    input_path = Path(input_path).resolve(strict=True)
    output_dir = Path(output_dir).absolute()
    if output_dir.exists() or output_dir.is_symlink():
        raise FileExistsError('Output directory already exists; choose a new directory.')
    if input_path.is_relative_to(output_dir):
        raise ValueError('Output directory must not contain the input.')
    pending = load_pending(pending_path)
    input_sha = file_sha(input_path)
    if input_sha == BASELINE_SHA256 and pending_path is None:
        raise ValueError('The research baseline requires --pending-rules with the separately held 27-combination rules.')
    sources = {p.name: file_sha(p) for p in sorted((HERE / '_revision').glob('*.py'))}
    provenance = {'entrypoint_sha256': file_sha(__file__), 'rule_files': sources, 'pending_rules_sha256': file_sha(pending_path) if pending_path else None}
    ruleset_hash = hashlib.sha256(canonical(provenance).encode('utf-8')).hexdigest()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.metadata-publish-', dir=output_dir.parent))
    counts = Counter()
    rows_count = 0
    dictionary_count = 0
    db = None
    try:
        db = sqlite3.connect(temporary / 'work.sqlite')
        db.executescript('CREATE TABLE records(id TEXT PRIMARY KEY); CREATE TABLE items(id TEXT PRIMARY KEY, payload TEXT NOT NULL, freq INTEGER NOT NULL, example_id TEXT NOT NULL, min_year TEXT NOT NULL, max_year TEXT NOT NULL);')
        opener = gzip.open if input_path.suffix == '.gz' else Path.open
        with opener(input_path, 'rt' if input_path.suffix == '.gz' else 'r', encoding='utf-8-sig', newline='') as source, csv_output(temporary / 'cleaned_metadata.csv.gz', HEADERS + EXTRA) as main, csv_output(temporary / 'record_match_bridge.csv.gz', BRIDGE) as bridge:
            reader = csv.reader(source, strict=True)
            if next(reader, None) != HEADERS:
                raise ValueError('Input must have the exact 31-column v1.2.11 schema; see examples.')
            for ordinal, before in enumerate(reader, 1):
                if len(before) != len(HEADERS) or not before[0]:
                    raise ValueError('Invalid baseline CSV row at ordinal ' + str(ordinal))
                try:
                    db.execute('INSERT INTO records VALUES (?)', (before[0],))
                except sqlite3.IntegrityError as error:
                    raise ValueError('Duplicate record_id at ordinal ' + str(ordinal)) from error
                after, _ = rule.update(before)
                if len(after) != len(HEADERS) or any(after[i] != before[i] for i in PROTECTED):
                    raise ValueError('Frozen identity or raw fields changed at ordinal ' + str(ordinal))
                if after[5] in {'C', 'X'} and after[4]:
                    raise ValueError('A multi-occupation or empty-occupation row has a nonempty parent core.')
                flag = pending.get(canonical([after[i] for i in (2, 9, 15, 28)]), '')
                values = routing(after, flag)
                key = item_key(after, flag)
                mid = item_id(key)
                main.writerow(after + [mid] + values + [ruleset_hash])
                bridge.writerow([after[0], mid, values[0], rule.VERSION, ruleset_hash])
                db.execute('INSERT INTO items VALUES (?, ?, 1, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET freq=freq+1, min_year=min(min_year,excluded.min_year), max_year=max(max_year,excluded.max_year)', (mid, key, after[0], after[1], after[1]))
                counts[values[0]] += 1
                rows_count += 1
                if ordinal % 10000 == 0:
                    db.commit()
        db.commit()
        with csv_output(temporary / 'job_match_dictionary.csv.gz', ['final_match_item_id'] + KEY_NAMES + ['freq', 'example_record_id', 'first_year', 'last_year', 'ruleset_version', 'ruleset_hash']) as writer:
            total = 0
            for mid, payload, freq, sample, first, last in db.execute('SELECT id,payload,freq,example_id,min_year,max_year FROM items ORDER BY freq DESC,id'):
                if item_id(payload) != mid:
                    raise ValueError('Dictionary identity mismatch.')
                writer.writerow([mid] + json.loads(payload) + [str(freq), sample, first, last, rule.VERSION, ruleset_hash])
                total += freq
                dictionary_count += 1
        if total != rows_count or db.execute('SELECT count(*) FROM records').fetchone()[0] != rows_count:
            raise ValueError('Record preservation or dictionary frequency check failed.')
        db.close()
        db = None
        (temporary / 'work.sqlite').unlink()
        files = {name: {'sha256': file_sha(temporary / name), 'bytes': (temporary / name).stat().st_size} for name in ['cleaned_metadata.csv.gz', 'job_match_dictionary.csv.gz', 'record_match_bridge.csv.gz']}
        manifest = {'status': 'REVISION_COMPLETE', 'scope': 'Sealed v1.2.11 metadata to v1.2.12 revision; not raw-to-final reproduction.', 'rows': rows_count, 'dictionary_items': dictionary_count, 'dictionary_frequency_sum': total, 'routes': dict(counts), 'research_version': rule.VERSION, 'input_sha256': input_sha, 'input_matches_research_baseline': input_sha == BASELINE_SHA256, 'private_pending_rules_loaded': pending_path is not None, 'ruleset_hash': ruleset_hash, 'ruleset_provenance': provenance, 'files': files, 'human_gold_standard': False, 'new_accuracy_estimate': None}
        (temporary / 'provenance.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        if output_dir.exists() or output_dir.is_symlink():
            raise FileExistsError('Output directory appeared during processing.')
        os.rename(temporary, output_dir)
        return manifest
    except BaseException:
        if db is not None:
            db.close()
        shutil.rmtree(temporary)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='CSV or CSV.gz with the sealed v1.2.11 31-column schema.')
    parser.add_argument('--output-dir', type=Path, required=True, help='A new output directory.')
    parser.add_argument('--pending-rules', type=Path, help='Optional private local unresolved-combination JSON.')
    args = parser.parse_args(argv)
    manifest = run(args.input, args.output_dir, args.pending_rules)
    print(json.dumps({'status': manifest['status'], 'rows': manifest['rows'], 'dictionary_items': manifest['dictionary_items']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
