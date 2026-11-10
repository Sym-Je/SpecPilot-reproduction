"""Stop only the two identity-matched server groups of a failed source preflight."""

import argparse
import json
import os
from pathlib import Path
import signal
import time


def stop(directory):
    if os.geteuid() != 0:
        raise RuntimeError('trusted pod cleanup requires the existing root runner identity')
    directory = Path(directory).absolute()
    if not directory.name.startswith('round-') or not directory.parent.parent.name.startswith('sp-source-'):
        raise ValueError('only source preflight server records are accepted')
    stopped = []
    for name in ('stock', 'candidate'):
        record = json.loads((directory / f'{name}.process.json').read_text())
        process = Path('/proc') / str(record['pid'])
        if not process.exists():
            stopped.append(dict(arm=name, already_gone=True))
            continue
        ticks = int((process / 'stat').read_text().rsplit(')', 1)[1].split()[19])
        command = (process / 'cmdline').read_bytes().decode(errors='replace')
        if (ticks != record['start_ticks'] or os.getpgid(record['pid']) != record['pid'] or
                'sglang.launch_server' not in command):
            raise RuntimeError('server identity changed; refuse cleanup')
        os.killpg(record['pid'], signal.SIGTERM)
        stopped.append(dict(arm=name, pid=record['pid'], start_ticks=ticks, term_sent=True))
    time.sleep(5)
    for row in stopped:
        if row.get('already_gone'):
            continue
        try:
            process = Path('/proc') / str(row['pid'])
            if not process.exists():
                continue
            ticks = int((process / 'stat').read_text().rsplit(')', 1)[1].split()[19])
            if ticks == row['start_ticks'] and os.getpgid(row['pid']) == row['pid']:
                os.killpg(row['pid'], signal.SIGKILL)
                row['kill_sent'] = True
        except ProcessLookupError:
            pass
    return stopped


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    print(json.dumps(stop(parser.parse_args().directory)), flush=True)
