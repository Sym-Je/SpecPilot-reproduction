"""Losslessly compress finished, derived timelines; retain raw traces and CSVs."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import time


def archive(directory):
    state = json.loads((directory / 'state.json').read_text())
    restoring_after_export = ((directory / 'restored-baseline/owner.json').exists()
                              and (directory / 'profile-summary.json').exists())
    assert state.get('measurement_finished_epoch') or restoring_after_export, 'Never archive active collection or export'
    record = directory / 'timeline-archive.json'
    history = json.loads(record.read_text()) if record.exists() else {'files': []}
    for source in sorted((directory / 'traces').rglob('trace_view.json')):
        destination = source.with_suffix('.json.gz')
        assert not destination.exists(), 'Inspect previous partial archive before resuming'
        original_bytes = source.stat().st_size
        with source.open('rb') as stream:
            checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        temporary = destination.with_suffix('.gz.tmp')
        with source.open('rb') as inp, gzip.open(temporary, 'wb', compresslevel=1) as out:
            shutil.copyfileobj(inp, out, 1024 * 1024)
        with gzip.open(temporary, 'rb') as inp:
            assert hashlib.file_digest(inp, 'sha256').hexdigest() == checksum, 'Compressed timeline verification failed'
        temporary.replace(destination)
        entry = {'original': str(source.relative_to(directory)), 'compressed': str(destination.relative_to(directory)),
                 'original_sha256': checksum, 'original_bytes': original_bytes,
                 'compressed_bytes': destination.stat().st_size, 'verified_round_trip': True}
        history['files'].append(entry)
        history.update(updated_epoch=time.time(), scope='Derived timeline storage only; raw profiler data and kernel CSVs unchanged')
        tmp = record.with_suffix('.tmp'); tmp.write_text(json.dumps(history, indent=2)); tmp.replace(record)
        source.unlink()
        print(json.dumps({'timeline': str(destination), 'saved_bytes': original_bytes - destination.stat().st_size}), flush=True)
    history['status'] = 'complete'
    record.write_text(json.dumps(history, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('directory', type=Path)
    archive(parser.parse_args().directory)
