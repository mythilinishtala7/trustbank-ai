import { MockAgentProvider } from './mock';
import { AdkAgentProvider } from './adk';
import type { AgentProvider } from './types';

export * from './types';
export { MockAgentProvider, deterministicExplanation, DEFAULT_QUESTIONS } from './mock';
export { validateExplanation, validateQuestions } from './guard';
export { AdkAgentProvider } from './adk';

/**
 * AGENT_MODE=adk -> Gemini via Google ADK (Vertex AI or API key, per ADK env vars).
 * Anything else -> deterministic mock agents (no keys needed).
 */
export function createAgentProvider(env: NodeJS.ProcessEnv = process.env): AgentProvider {
  return env['AGENT_MODE'] === 'adk' ? new AdkAgentProvider() : new MockAgentProvider();
}
