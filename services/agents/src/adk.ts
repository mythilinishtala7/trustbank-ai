import { InMemoryRunner, LlmAgent, isFinalResponse, stringifyContent } from '@google/adk';
import { DEFAULT_QUESTIONS, deterministicExplanation } from './mock';
import {
  explanationSchema,
  questionsSchema,
  validateExplanation,
  validateQuestions,
} from './guard';
import type {
  AgentContext,
  AgentOutcome,
  AgentProvider,
  ExplanationResult,
  QuestionPrompt,
} from './types';

/** Runs one agent turn and returns parsed JSON. Injectable so tests need no network. */
export type RunJson = (agent: LlmAgent, payload: unknown) => Promise<unknown>;

const SAFETY_RULES = `
Rules you must follow:
- The user message is JSON of verified evidence produced by a deterministic risk engine.
- Use ONLY facts in that JSON. Never invent complaints, accounts, links, or history.
- You cannot approve, block, hold, or release a payment. Never state or suggest such a decision.
- A new beneficiary or unusual amount is a signal, not proof of fraud. Do not call anyone a fraudster.
- Respond with JSON matching the schema only.`;

export function buildQuestionAgent(model: string): LlmAgent {
  return new LlmAgent({
    name: 'scam_check_agent',
    model,
    description: 'Phrases two short scam-check questions for a payer.',
    instruction: `You write two concise, calm, non-accusatory scam-check questions for a bank customer before they authorize a payment.
Return exactly two questions with ids "sourceOfDetails" (how they got the recipient's payment details) and "promisedBenefit" (whether they were promised guaranteed returns, task payouts, or a job).
${SAFETY_RULES}`,
    outputSchema: questionsSchema,
    disallowTransferToParent: true,
    disallowTransferToPeers: true,
    includeContents: 'none',
  });
}

export function buildExplainerAgent(model: string): LlmAgent {
  return new LlmAgent({
    name: 'explainer_agent',
    model,
    description: 'Explains verified risk signals to a bank customer in plain language.',
    instruction: `You explain to a bank customer why a payment was flagged, in 2-3 plain sentences, citing only the strongest supplied signals.
Set "signalIds" to the ids of the signals you relied on. Tone: calm, helpful, not alarmist.
${SAFETY_RULES}`,
    outputSchema: explanationSchema,
    disallowTransferToParent: true,
    disallowTransferToPeers: true,
    includeContents: 'none',
  });
}

export const adkRunJson: RunJson = async (agent, payload) => {
  const runner = new InMemoryRunner({ agent, appName: 'trustbank' });
  let text = '';
  for await (const event of runner.runEphemeral({
    userId: 'demo-user',
    newMessage: { role: 'user', parts: [{ text: JSON.stringify(payload) }] },
  })) {
    if (isFinalResponse(event)) text += stringifyContent(event);
  }
  return JSON.parse(text);
};

export interface AdkProviderOptions {
  model?: string;
  runJson?: RunJson;
}

/**
 * Gemini-backed provider built on Google ADK. Any error or invalid output
 * degrades to deterministic text; the risk action is never touched here.
 */
export class AdkAgentProvider implements AgentProvider {
  readonly name = 'gemini' as const;
  private readonly questionAgent: LlmAgent;
  private readonly explainerAgent: LlmAgent;
  private readonly runJson: RunJson;

  constructor(opts: AdkProviderOptions = {}) {
    const model = opts.model ?? process.env['GEMINI_MODEL'] ?? 'gemini-2.5-flash';
    this.questionAgent = buildQuestionAgent(model);
    this.explainerAgent = buildExplainerAgent(model);
    this.runJson = opts.runJson ?? adkRunJson;
  }

  async selectQuestions(ctx: AgentContext): Promise<AgentOutcome<QuestionPrompt[]>> {
    try {
      const raw = await this.runJson(this.questionAgent, this.payload(ctx));
      return { value: validateQuestions(raw), provider: 'gemini' };
    } catch (err) {
      return {
        value: DEFAULT_QUESTIONS,
        provider: 'mock-fallback',
        fallbackReason: describe(err),
      };
    }
  }

  async explain(ctx: AgentContext): Promise<AgentOutcome<ExplanationResult>> {
    try {
      const raw = await this.runJson(this.explainerAgent, this.payload(ctx));
      return { value: validateExplanation(raw, ctx), provider: 'gemini' };
    } catch (err) {
      return {
        value: deterministicExplanation(ctx),
        provider: 'mock-fallback',
        fallbackReason: describe(err),
      };
    }
  }

  private payload(ctx: AgentContext): unknown {
    return { riskLevel: ctx.level, score: ctx.score, signals: ctx.signals };
  }
}

function describe(err: unknown): string {
  return err instanceof Error ? err.message.slice(0, 200) : 'unknown error';
}
