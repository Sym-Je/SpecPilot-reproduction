"""Private hash-only cohort selection; request bodies load only after candidate freeze."""

import json
import gzip
import hashlib
from pathlib import Path

from controller.http_transport import sha_ids
from controller.paper_policy import valid_digest
from controller.scored_forcing import digest_record, read_reference
from controller.scoring import checked_tokens
from controller.sealed_protocol import _frozen, _private, _save, _separate


INDEX = 'controller-request-index-v1'
EXCLUSIONS = 'controller-phase4-exclusions-v1'
PLAN = 'controller-phase4-cohort-plan-v1'


def source_catalog_sha256():
    from exp.generalization_data import REVISIONS, SOURCES
    return digest_record(dict(revisions=REVISIONS, sources=SOURCES))


def cache_from_public(preparation, private_source_root, destination):
    """Host metadata only: never stat/read the old private source tree or its selected dataset."""
    from exp.generalization_data import REVISIONS, SOURCES
    private_source_root = Path(private_source_root)
    if not private_source_root.is_absolute() or '..' in private_source_root.parts:
        raise ValueError('absolute private cache path metadata required')
    summary = read_reference(preparation, Path(preparation['path']).parent)
    expected = {(repo, filename) for repo, filename, license_name in SOURCES.values()}
    sources = summary['sources']
    if (not valid_digest(summary.get('dataset_sha256')) or
            {(item['repo'], item['filename']) for item in sources} != expected or len(sources) != len(expected)):
        raise ValueError('complete pinned public source inventory and used dataset SHA required')
    metadata = []
    for item in sources:
        if item['revision'] != REVISIONS[item['repo']] or not valid_digest(item['sha256']):
            raise ValueError('public source revision/SHA differs from the fixed catalog')
        name = item['repo'].replace('/', '--') + '--' + Path(item['filename']).name
        metadata.append(dict(item, path=str(private_source_root / name)))
    destination = Path(destination).absolute()
    destination.mkdir(mode=0o700)
    _private(destination, directory=True)
    cache = _save(destination / 'sources.json', metadata)
    used = dict(path=str(private_source_root / 'dataset.json'), sha256=summary['dataset_sha256'])
    _save(destination / 'cache-provenance.json', dict(preparation=preparation, source_cache=cache, used_sources=[used]))
    return dict(source_cache=cache, used_sources=[used])


def generate_indexes(freeze, destination, specification, *, tokenizer=None):
    """Runs only inside the final controller job; never reuse old selected rows as a pool."""
    root, frozen = _frozen(freeze)
    from exp.generalization_data import SOURCES, download_sources, duplicate, source_rows
    from exp.p3_pair_run import SUITES
    if (specification['source_catalog_sha256'] != source_catalog_sha256() or
            set(specification['dev_sources']) != set(SUITES) or
            any(suite not in SOURCES for suite in specification['counts']) or
            type(specification['pool_per_suite']) is not int or specification['pool_per_suite'] < 1):
        raise ValueError('fixed public revisions, all five original dev sources and blind pool size required')
    destination = Path(destination).absolute()
    _separate(destination, frozen['research_roots'])
    destination.mkdir(mode=0o700)
    _private(destination, directory=True)
    for name in ('dev', 'used', 'pool', 'downloads'):
        (destination / name).mkdir(mode=0o700)
    if tokenizer is None:
        from transformers import AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(frozen['launch_protocol']['model_path'], local_files_only=True)
    def encode(prompt):
        values = tokenizer.apply_chat_template([dict(role='user', content=prompt)],
            add_generation_prompt=True, tokenize=True, enable_thinking=True)
        values = list(values if isinstance(values, list) else values['input_ids'])
        checked_tokens(values)
        return values
    model = Path(frozen['launch_protocol']['model_path'])
    tokenizer_files = {name: hashlib.sha256((model / name).read_bytes()).hexdigest() for name in
        ('tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'tokenizer.model', 'chat_template.jinja')
        if (model / name).is_file()}
    if not tokenizer_files:
        raise ValueError('concrete tokenizer/template identity required')
    protocol = digest_record(dict(tokenizer=tokenizer_files, model=frozen['launch_protocol']['model_path'],
        template='one user message; tokenize=True; add_generation_prompt=True; enable_thinking=True'))
    _save(destination / 'tokenizer-identity.json', dict(prompt_protocol_sha256=protocol, files=tokenizer_files))
    originals, prompts, dev_entries = [], [], []
    for suite in SUITES:
        source = specification['dev_sources'][suite]
        source_path = Path(source['path'])
        if source_path.is_symlink():
            raise ValueError('authoritative full-dev source must be a concrete file')
        content = source_path.read_bytes()
        if hashlib.sha256(content).hexdigest() != source['sha256']:
            raise ValueError('full dev source differs from its authoritative metadata SHA')
        rows = [json.loads(line) for line in content.decode().splitlines() if line]
        if len(rows) != 20:
            raise ValueError('exactly all 100 original dev records required, twenty per suite')
        for row in rows:
            prompt = row['turns'][0]
            values = encode(prompt)
            prompts.append(prompt)
            originals.append(dict(row, suite=suite))
            dev_entries.append(dict(id=row['id'], suite=suite, input_sha256=sha_ids(values)))
    dev_index = _save(destination / 'dev/index.json', dict(schema=INDEX, kind='dev',
        prompt_protocol_sha256=protocol, entries=dev_entries, sources=specification['dev_sources']))
    used_entries = []
    for source in specification['used_sources']:
        value = read_reference(source, Path(source['path']).parent)
        rows = value.get('requests', value.get('entries'))
        if not isinstance(rows, list):
            raise ValueError('every used manifest must enumerate actual requests/input hashes')
        for row in rows:
            checksum = row['input_sha256']
            if not valid_digest(checksum) or ('input_ids' in row and sha_ids(row['input_ids']) != checksum):
                raise ValueError('used manifest input hash is invalid')
            used_entries.append(dict(id=f'used-{len(used_entries):06d}', suite=row['suite'], input_sha256=checksum))
        prompts.extend(item['prompt'] for item in value.get('items', []) if isinstance(item.get('prompt'), str))
    used_indexes = []
    if used_entries:
        used_indexes.append(_save(destination / 'used/index.json', dict(schema=INDEX, kind='used',
            prompt_protocol_sha256=protocol, entries=used_entries, sources=specification['used_sources'])))
    cache = specification.get('source_cache')
    if cache is not None:
        read_reference(cache, Path(cache['path']).parent)
    downloads = download_sources(destination / 'downloads', cache=Path(cache['path']).parent if cache else None)
    entries, accepted_prompts = [], []
    excluded_hashes = {entry['input_sha256'] for entry in dev_entries + used_entries}
    seen = set()
    for suite in sorted(specification['counts']):
        repo, filename, license_name = SOURCES[suite]
        source = downloads[repo, filename]
        content = Path(source['path']).read_bytes()
        if hashlib.sha256(content).hexdigest() != source['sha256']:
            raise ValueError('downloaded fixed source differs from recorded content hash')
        decoded = gzip.decompress(content).decode() if filename.endswith('.gz') else content.decode()
        rows = [json.loads(line) for line in decoded.splitlines() if line] if '.jsonl' in filename else json.loads(decoded)
        pool = sorted(source_rows(suite, rows), key=lambda row: digest_record(dict(seed=specification['seed'],
                      suite=suite, source_id=row['source_id'])))[:specification['pool_per_suite']]
        old_ids = {str(row.get('task_id', row['id'].removeprefix(suite + '-'))) for row in originals if row['suite'] == suite}
        for item in pool:
            if item['source_id'] in old_ids or duplicate(item['prompt'], prompts + accepted_prompts):
                continue
            values = encode(item['prompt'])
            checksum = sha_ids(values)
            if not 0 < len(values) <= 8192 or checksum in excluded_hashes or checksum in seen:
                continue
            seen.add(checksum)
            accepted_prompts.append(item['prompt'])
            identifier = 'pool-' + digest_record(dict(suite=suite, source_id=item['source_id']))[:24]
            request = dict(id=identifier, suite=suite, turn=0, input_ids=values, input_sha256=checksum)
            reference = _save(destination / 'pool' / f'{identifier}.json', request)
            entries.append(dict(id=identifier, suite=suite, input_sha256=checksum, request=reference))
    index = _save(destination / 'pool/index.json', dict(schema=INDEX, kind='pool',
        prompt_protocol_sha256=protocol, entries=entries, sources=list(downloads.values()),
        source_catalog_sha256=specification['source_catalog_sha256'], seed=specification['seed'],
        pool_per_suite=specification['pool_per_suite']))
    return dict(pool_index=index, dev_indexes=[dev_index], used_indexes=used_indexes,
                counts=specification['counts'], seed=specification['seed'])


def _load(reference):
    path = _private(reference['path'])
    _private(path.parent, directory=True)
    return read_reference(reference, path.parent)


def _index(reference, kind):
    value = _load(reference)
    entries = value.get('entries')
    if (value.get('schema') != INDEX or value.get('kind') != kind or
            not valid_digest(value.get('prompt_protocol_sha256')) or not isinstance(entries, list) or not entries):
        raise ValueError('complete private index and prompt protocol required')
    identifiers = set()
    for entry in entries:
        if (not isinstance(entry.get('id'), str) or not entry['id'] or entry['id'] in identifiers or
                not isinstance(entry.get('suite'), str) or not entry['suite'] or
                not valid_digest(entry.get('input_sha256'))):
            raise ValueError('invalid or duplicate indexed request identity')
        identifiers.add(entry['id'])
        if kind == 'pool':
            source = entry['request']
            if not valid_digest(source.get('sha256')) or not Path(source['path']).is_absolute():
                raise ValueError('pool record needs an immutable private request reference')
            if not Path(source['path']).resolve().is_relative_to(Path(reference['path']).parent.resolve()):
                raise ValueError('pool record escapes its physically separate pool root')
    return value


def build_exclusions(path, *, dev_indexes, used_indexes=()):
    """Trusted maintainer must supply ALL authoritative dev indexes, not a measured subset."""
    if not dev_indexes:
        raise ValueError('all-dev source indexes are required')
    path = Path(path).absolute()
    _private(path.parent, directory=True)
    sources = [('dev', source) for source in dev_indexes] + [('used', source) for source in used_indexes]
    if len({source['sha256'] for kind, source in sources}) != len(sources):
        raise ValueError('duplicate exclusion index')
    indexes = [_index(source, kind) for kind, source in sources]
    protocols = {value['prompt_protocol_sha256'] for value in indexes}
    if len(protocols) != 1:
        raise ValueError('dev/used prompt tokenization protocols differ')
    hashes = sorted({entry['input_sha256'] for value in indexes for entry in value['entries']})
    return _save(path, dict(schema=EXCLUSIONS, prompt_protocol_sha256=protocols.pop(),
        dev_indexes=list(dev_indexes), used_indexes=list(used_indexes), input_hashes=hashes,
        scope='all supplied authoritative dev indexes plus all supplied used inputs; completeness owned by maintainer'))


def load_exclusions(reference):
    result = _load(reference)
    if result.get('schema') != EXCLUSIONS or not result.get('dev_indexes'):
        raise ValueError('all-dev exclusion provenance missing')
    indexes = [_index(source, kind) for kind, name in (('dev', 'dev_indexes'), ('used', 'used_indexes'))
               for source in result[name]]
    hashes = sorted({entry['input_sha256'] for value in indexes for entry in value['entries']})
    if (hashes != result['input_hashes'] or
            any(value['prompt_protocol_sha256'] != result['prompt_protocol_sha256'] for value in indexes)):
        raise ValueError('exclusions differ from their frozen full source indexes')
    return result


def plan_cohort(path, *, pool_index, exclusions, counts, seed):
    path = Path(path).absolute()
    _private(path.parent, directory=True)
    pool, excluded = _index(pool_index, 'pool'), load_exclusions(exclusions)
    if (pool['prompt_protocol_sha256'] != excluded['prompt_protocol_sha256'] or
            not isinstance(counts, dict) or not counts or any(not isinstance(key, str) or not key or
            type(value) is not int or value < 1 for key, value in counts.items()) or
            not isinstance(seed, str) or not seed):
        raise ValueError('predeclared cohort counts, seed and identical prompt protocol required')
    pool_root = Path(pool_index['path']).parent.resolve()
    for source in excluded['dev_indexes'] + excluded['used_indexes']:
        other = Path(source['path']).parent.resolve()
        if pool_root.is_relative_to(other) or other.is_relative_to(pool_root):
            raise ValueError('pool and dev/used indexes must be physically separate')
    return _save(path, dict(schema=PLAN, pool_index=pool_index, exclusions=exclusions,
        counts=counts, seed=seed, prompt_protocol_sha256=pool['prompt_protocol_sha256']))


def _choose(plan):
    pool, excluded = _index(plan['pool_index'], 'pool'), load_exclusions(plan['exclusions'])
    if not pool['prompt_protocol_sha256'] == excluded['prompt_protocol_sha256'] == plan['prompt_protocol_sha256']:
        raise ValueError('prompt protocol drifted')
    rejected = set(excluded['input_hashes'])
    ordered = sorted(pool['entries'], key=lambda entry: digest_record(dict(seed=plan['seed'],
        id=entry['id'], suite=entry['suite'], input_sha256=entry['input_sha256'])))
    chosen, seen = [], set()
    for suite, count in sorted(plan['counts'].items()):
        candidates = []
        for entry in ordered:
            if entry['suite'] != suite or entry['input_sha256'] in rejected or entry['input_sha256'] in seen:
                continue
            seen.add(entry['input_sha256'])
            candidates.append(entry)
            if len(candidates) == count:
                break
        if len(candidates) != count:
            raise ValueError('insufficient unseen requests for the predeclared cohort; no adaptive replacement')
        chosen.extend(candidates)
    return chosen, len(pool['entries']), sum(entry['input_sha256'] in rejected for entry in pool['entries'])


def select_cohort(freeze):
    """Hash-only selection; seed/counts/index identities must be artifacts in candidate freeze."""
    root, frozen = _frozen(freeze)
    source = frozen['artifacts']['cohort_plan']
    plan = _load(source)
    if plan.get('schema') != PLAN:
        raise ValueError('cohort plan must be frozen before selection')
    _separate(Path(plan['pool_index']['path']).parent.resolve(), frozen['research_roots'])
    excluded = load_exclusions(plan['exclusions'])
    if not set(excluded['input_hashes']).issubset(frozen['seen_input_hashes']):
        raise ValueError('candidate freeze omitted dev/used input hashes')
    chosen, total, rejected = _choose(plan)
    return _save(root / 'cohort-selection.json', dict(schema=PLAN, freeze_sha256=freeze['sha256'],
        plan=source, chosen=chosen, summary=dict(counts=plan['counts'], selected=len(chosen),
        pool_records=total, excluded_records=rejected, prompt_protocol_sha256=plan['prompt_protocol_sha256'])))


def _materialized(freeze, selection):
    root, frozen = _frozen(freeze)
    selected = read_reference(selection, root)
    if selected.get('freeze_sha256') != freeze['sha256'] or selected['plan'] != frozen['artifacts']['cohort_plan']:
        raise ValueError('selection differs from the frozen candidate')
    plan = _load(selected['plan'])
    chosen, total, rejected = _choose(plan)
    if chosen != selected['chosen']:
        raise ValueError('selection differs from the preregistered blind ranking')
    pool_root = Path(plan['pool_index']['path']).parent.resolve()
    requests = []
    for number, entry in enumerate(chosen):
        source = _private(entry['request']['path'])
        _private(source.parent, directory=True)
        _separate(source, frozen['research_roots'])
        request = read_reference(entry['request'], pool_root)
        checked_tokens(request['input_ids'])
        if (request.get('id') != entry['id'] or request.get('suite') != entry['suite'] or request.get('turn') != 0 or
                request.get('input_sha256') != entry['input_sha256'] or sha_ids(request['input_ids']) != entry['input_sha256']):
            raise ValueError('indexed hash differs from the original private request')
        requests.append(dict(request, id=f'phase4-{number:06d}'))
    return root, requests, selected['summary']


def materialize_cohort(freeze, selection):
    """Only a controller process may call this; no body is returned to the broker/model."""
    root, requests, summary = _materialized(freeze, selection)
    return _save(root / 'cohort-requests.json', requests)


def verify_cohort(freeze, selection, requests):
    root, expected, summary = _materialized(freeze, selection)
    if read_reference(requests, root) != expected:
        raise ValueError('materialized cohort differs from its original private pool records')
    return summary


def cohort_summary(selection, *, private_root):
    return read_reference(selection, private_root)['summary']
