"""Offline stock diagnostic adapter for a pinned, reviewed BBuf skill subset."""

import argparse
import json
from pathlib import Path

from harness.skill_diagnostics import analyze


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--tools', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    arguments = parser.parse_args()
    result = analyze(arguments.manifest, arguments.tools, arguments.output)
    print(json.dumps(dict(engineering_passed=result['engineering_passed'],
        gpu_submissions=0, controller_accepted=False, result=str(arguments.output / 'result.json'))))
    return 0 if result['engineering_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
