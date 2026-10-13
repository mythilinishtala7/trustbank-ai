import { z } from 'zod';
import type { AgentContext, ExplanationResult, QuestionId, QuestionPrompt } from './types';

export const questionsSchema = z.object({
  questions: z
    .array(
      z.object({
        id: z.enum(['sourceOfDetails', 'promisedBenefit']),
        text: z.string().min(10).max(200),
      }),
    )
    .min(1)
    .max(2),
});

export const explanationSchema = z.object({
  headline: z.string().min(3).max(80),
  summary: z.string().min(20).max(500),
  signalIds: z.array(z.string()).max(5),
});

/** Reject output that references unknown ids or duplicates questions. Throws on invalid. */
export function validateQuestions(raw: unknown): QuestionPrompt[] {
  const parsed = questionsSchema.parse(raw);
  const seen = new Set<QuestionId>();
  for (const q of parsed.questions) {
    if (seen.has(q.id)) throw new Error(`duplicate question ${q.id}`);
    seen.add(q.id);
  }
  return parsed.questions;
}

/** Explanation must be grounded in supplied signal ids; unknown ids mean invented evidence. */
export function validateExplanation(raw: unknown, ctx: AgentContext): ExplanationResult {
  const parsed = explanationSchema.parse(raw);
  const known = new Set(ctx.signals.map((s) => s.id));
  const unknown = parsed.signalIds.filter((id) => !known.has(id));
  if (unknown.length > 0) throw new Error(`unknown signal ids: ${unknown.join(',')}`);
  if (ctx.signals.some((s) => s.severity !== 'info') && parsed.signalIds.length === 0) {
    throw new Error('explanation cites no signals');
  }
  return parsed;
}
