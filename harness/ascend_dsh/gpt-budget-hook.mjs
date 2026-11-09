// Every native DSH GPT request is pre-admitted; never a network relay.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
export const name = 'specpilot-gpt-budget';
export const inject = ['llm'];
const here = dirname(fileURLToPath(import.meta.url));
function operation(action, value) {
  return JSON.parse(execFileSync('/usr/local/python3.12.13/bin/python3.12',
    [join(here, 'gpt_budget.py'), action], {input: JSON.stringify(value), encoding: 'utf8',
    timeout: 120000, maxBuffer: 16384, stdio: ['pipe', 'pipe', 'pipe']}));
}
export function apply(ctx) {
  ctx.on('llm/stream', (options, next) => (async function* () {
    if (options.model !== 'gpt-6.1-sol' || options.provider !== 'dreamwalk' || options.reasoningEffort !== 'xhigh')
      throw new Error('Only budgeted gpt-6.1-sol / Responses / xhigh is allowed');
    const encoded = JSON.stringify({messages: options.messages, tools: options.tools});
    const admitted = operation('reserve', {model: options.model,
      input_bytes: Buffer.byteLength(encoded, 'utf8'), max_tokens: options.maxTokens,
      request_sha256: createHash('sha256').update(encoded).digest('hex'),
      purpose: options.purpose ?? 'conversation', role_id: process.env.SP_ROLE_ID ?? 'unknown'});
    let usage = null, finish = null;
    try {
      for await (const chunk of next()) {
        if (chunk.type === 'usage') usage = chunk;
        if (chunk.type === 'finish') finish = chunk;
        yield chunk;
      }
    } finally { operation('settle', {reservation_id: admitted.reservation_id, usage, finish}); }
  })());
}
