// Native DSH llm/stream middleware. NorthGate calls remain direct HTTPS.
// Applies to EVERY LLM request, including any auxiliary producer/retry.
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

export const name = 'specpilot-budget';
export const inject = ['llm'];
const here = dirname(fileURLToPath(import.meta.url));
function operation(action, value) {
  const result = execFileSync('/usr/local/python3.12.13/bin/python3.12',
    [join(here, 'budget.py'), action], {
      input: JSON.stringify(value), encoding: 'utf8', timeout: 120000,
      maxBuffer: 16384, stdio: ['pipe', 'pipe', 'pipe'],
    });
  return JSON.parse(result);
}
export function apply(ctx) {
  ctx.on('llm/stream', (options, next) => (async function* () {
    if (options.model !== 'claude-opus-5-5' || options.provider !== 'deepseek-official') {
      throw new Error('Only budgeted Claude 5.5 route is allowed');
    }
    const encoded = JSON.stringify({ messages: options.messages, tools: options.tools });
    const admitted = operation('reserve', {
      model: options.model, input_bytes: Buffer.byteLength(encoded, 'utf8'),
      max_tokens: options.maxTokens, request_sha256: createHash('sha256').update(encoded).digest('hex'),
      purpose: options.purpose ?? 'conversation',
      role_id: process.env.SP_ROLE_ID ?? 'unknown',
    });
    let usage = null;
    let finish = null;
    try {
      for await (const chunk of next()) {
        if (chunk.type === 'usage') usage = chunk;
        if (chunk.type === 'finish') finish = chunk;
        yield chunk;
      }
    } finally {
      operation('settle', { reservation_id: admitted.reservation_id, usage, finish });
    }
  })());
}
