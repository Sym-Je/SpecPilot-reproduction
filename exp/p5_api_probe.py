"""Bounded real-engine interface probe; no performance or correctness verdict."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from controller.scoring import NativeClient
from exp.p3_pair_run import Server, arm_specs, check_ports, clean_environment, interrupted, wait_for_idle, write_json


class CorrectnessServer(Server):
    def launch_spec(self):
        role = self.arm['role']
        command = ['bash', str(ROOT / 'exp/p5_serve.sh'), role, self.gpu['uuid'], str(self.port)]
        environment = dict(self.environment, SP_ENGINE=self.arm['engine'],
                           P5_SERVER_LOG=str(self.output_dir / f'{self.arm["name"]}.server.log'))
        return command, environment


def run_probe(output, reference):
    environment = clean_environment()
    expected = os.environ['P5_EXPECTED_COMMIT']
    subprocess.run(['git', 'diff', '--exit-code', expected, '--', 'exp', 'harness', 'controller'], cwd=ROOT, check=True)
    signal.signal(signal.SIGTERM, interrupted)
    gpus = wait_for_idle([0, 1])
    check_ports([30120, 30130])
    arms, _ = arm_specs(['ar', 'stock'], environment)
    manifest = json.loads((reference / 'manifest.json').read_text())
    request = manifest['requests'][0]
    source = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
              ('controller/scoring.py', 'exp/p5_serve.sh', 'exp/p5_api_probe.py')}
    write_json(output / 'manifest.json', dict(source_pin=expected, source_sha256=source, gpus=gpus,
        request_id=request['id'], input_sha256=request['input_sha256'],
        reference_manifest_sha256=hashlib.sha256((reference / 'manifest.json').read_bytes()).hexdigest(),
        scope='short API capability probe; no performance, injection regression or lossless claim'))
    with ExitStack() as resources:
        specifications = [dict(arms[0], name='generator', role='ar'), dict(arms[0], name='scorer', role='scorer')]
        servers = [CorrectnessServer(arm, gpu, port, output, environment)
                   for arm, gpu, port in zip(specifications, gpus, (30120, 30130))]
        for server in servers:
            resources.callback(server.stop)
            server.start()
        for server in servers:
            server.wait_ready(900)
        generator = NativeClient('http://127.0.0.1:30120', output / 'generator-raw')
        scorer = NativeClient('http://127.0.0.1:30130', output / 'scorer-raw')
        identity = scorer.scorer_identity(arms[0]['tree_sha'])
        write_json(output / 'scorer-identity.json', identity)
        prompt = request['input_ids']
        generated = generator.post('/generate', dict(input_ids=prompt,
            sampling_params={'temperature': 0, 'top_k': 1, 'max_new_tokens': 8}))
        tokens = generated['output_ids']
        errors = []
        forced = prefix = None
        try:
            forced = scorer.score(prompt, tokens)
            prefix = scorer.score(prompt, tokens[:1])
            write_json(output / 'forced-scores.json', forced)
            write_json(output / 'prefix-scores.json', prefix)
            if forced['scores'][0]['token'] != prefix['scores'][0]['token']:
                raise ValueError('full/prefix forced token alignment differs')
        except Exception as error:
            errors.append(dict(capability='teacher_forced_scores', error=repr(error)))
        desired = (tokens[0] + 1) % 248320
        shape = []
        bias_passed = False
        try:
            biased = generator.post('/generate', dict(input_ids=prompt,
                sampling_params={'temperature': 0, 'top_k': 1, 'max_new_tokens': 2,
                                 'logit_bias': {str(desired): 100.0}}))
            if biased['output_ids'][0] != desired:
                raise ValueError('native logit_bias was not applied')
            bias_passed = True
        except Exception as error:
            errors.append(dict(capability='logit_bias', error=repr(error)))
        try:
            hidden = scorer.post('/generate', dict(input_ids=prompt,
                sampling_params={'temperature': 0, 'top_k': 1, 'max_new_tokens': 1}, return_hidden_states='last'))
            values = hidden.get('hidden_states', hidden.get('meta_info', {}).get('hidden_states'))
            if values is None:
                raise ValueError('enabled hidden-state API returned no evidence')
            current = values
            while isinstance(current, list) and current:
                shape.append(len(current))
                current = current[0]
        except Exception as error:
            errors.append(dict(capability='hidden_states', error=repr(error)))
        write_json(output / 'capabilities.json', dict(fp32_head_advertised=True,
            teacher_forced_input_logprobs=forced is not None and prefix is not None,
            forced_tokens=len(tokens), native_logit_bias=bias_passed, errors=errors,
            hidden_state_shape=shape,
            scope='capabilities only; full protocol and numerical head validation remain required'))
        if errors:
            raise ValueError(f'capability failures: {errors}')
    check_ports([30120, 30130])
    write_json(output / 'cleanup.json', wait_for_idle([0, 1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--reference', type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=False)
    try:
        run_probe(args.out_dir, args.reference)
    except BaseException as error:
        write_json(args.out_dir / 'failed.json', {'error': repr(error)})
        try:
            check_ports([30120, 30130])
            write_json(args.out_dir / 'failure-cleanup.json', wait_for_idle([0, 1]))
        except Exception as cleanup_error:
            write_json(args.out_dir / 'failure-cleanup-error.json', {'error': repr(cleanup_error)})
        raise


if __name__ == '__main__':
    main()
