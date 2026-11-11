"""Fixed CPU-only dependency adapter for a verified frozen collector audit."""

import json
import os
from pathlib import Path
import sys


def main():
    runtime, output = map(Path, sys.argv[1:])
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '' or not runtime.is_absolute() or not output.is_absolute():
        raise ValueError('explicit frozen runtime/output and disabled CUDA visibility required')
    sys.path.insert(0, str(runtime))
    import transformers
    from exp.profile_capture import audit
    result = audit(output)
    print(json.dumps(dict(result=result, runtime=dict(python=sys.version,
        executable=str(Path(sys.executable).resolve()), transformers=transformers.__version__,
        cuda_visible_devices='', scope='trusted CPU retokenization; not an OS sandbox or GPU experiment')),
        sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()
