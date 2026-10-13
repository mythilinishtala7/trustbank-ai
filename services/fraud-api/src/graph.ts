import type { GraphEdge, GraphNode } from './models';
import type { Store } from './store';

const HOUR = 3600_000;

export interface NetworkFacts {
  beneficiaryId: string;
  /** Distinct customers/entities that sent to this beneficiary within the window. */
  recentSenderIds: string[];
  /** Directly connected beneficiaries labelled FLAGGED in synthetic intel. */
  flaggedNeighborIds: string[];
}

export const VELOCITY_WINDOW_HOURS = 72;
export const VELOCITY_MIN_SENDERS = 3;

export function networkFacts(store: Store, beneficiaryId: string): NetworkFacts {
  const cutoff = store.clock().getTime() - VELOCITY_WINDOW_HOURS * HOUR;
  const transfers = store.transfers();
  const senders = new Set<string>();
  const neighbors = new Set<string>();
  for (const t of transfers) {
    if (t.to === beneficiaryId && new Date(t.timestamp).getTime() >= cutoff) senders.add(t.from);
    const other = t.from === beneficiaryId ? t.to : t.to === beneficiaryId ? t.from : undefined;
    if (other && store.beneficiaries.get(other)?.syntheticRisk === 'FLAGGED') neighbors.add(other);
  }
  return {
    beneficiaryId,
    recentSenderIds: [...senders].sort(),
    flaggedNeighborIds: [...neighbors].sort(),
  };
}

function riskLevelFor(store: Store, id: string): GraphNode['riskLevel'] {
  const b = store.beneficiaries.get(id);
  if (!b) return 'NORMAL';
  if (b.syntheticRisk === 'FLAGGED') return 'FLAGGED';
  const f = networkFacts(store, id);
  if (f.flaggedNeighborIds.length >= 2 || f.recentSenderIds.length >= VELOCITY_MIN_SENDERS) return 'WATCH';
  return 'NORMAL';
}

export function buildGraph(store: Store): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const transfers = store.transfers();
  const ids = new Set<string>();
  transfers.forEach((t) => {
    ids.add(t.from);
    ids.add(t.to);
  });

  const nodes: GraphNode[] = [...ids].sort().map((id) => {
    const b = store.beneficiaries.get(id);
    if (b) {
      return {
        id,
        type: 'beneficiary',
        label: b.displayName,
        riskLevel: riskLevelFor(store, id),
        metadata: { handle: b.handle, complaints: b.complaintCount, ...(b.firstSeenAt ? { firstSeenAt: b.firstSeenAt } : {}) },
      };
    }
    return {
      id,
      type: 'customer',
      label: store.customerNames.get(id) ?? id,
      riskLevel: 'NORMAL',
      metadata: {},
    };
  });

  const edges: GraphEdge[] = transfers.map((t) => ({
    id: t.id,
    source: t.from,
    target: t.to,
    amount: t.amount,
    timestamp: t.timestamp,
    status: t.status,
  }));
  return { nodes, edges };
}

export interface NodeDetail {
  node: GraphNode;
  /** Plain-language observations derived from graph data. Association is not proof. */
  observations: string[];
  connections: { nodeId: string; label: string; direction: 'in' | 'out'; amount: number; timestamp: string }[];
  disclaimer: string;
}

export function nodeDetail(store: Store, id: string): NodeDetail | undefined {
  const { nodes, edges } = buildGraph(store);
  const node = nodes.find((n) => n.id === id);
  if (!node) return undefined;
  const label = (nid: string) => nodes.find((n) => n.id === nid)?.label ?? nid;

  const connections = edges
    .filter((e) => e.source === id || e.target === id)
    .map((e) => ({
      nodeId: e.source === id ? e.target : e.source,
      label: label(e.source === id ? e.target : e.source),
      direction: (e.source === id ? 'out' : 'in') as 'in' | 'out',
      amount: e.amount,
      timestamp: e.timestamp,
    }))
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  const observations: string[] = [];
  if (node.type === 'beneficiary') {
    const f = networkFacts(store, id);
    const b = store.beneficiaries.get(id)!;
    if (b.syntheticRisk === 'FLAGGED') {
      observations.push(`Labelled FLAGGED in synthetic intel (${b.complaintCount} synthetic complaints).`);
    }
    if (f.recentSenderIds.length >= VELOCITY_MIN_SENDERS) {
      observations.push(
        `Received transfers from ${f.recentSenderIds.length} different senders in the last ${VELOCITY_WINDOW_HOURS} hours.`,
      );
    }
    if (f.flaggedNeighborIds.length > 0) {
      observations.push(
        `Directly connected to ${f.flaggedNeighborIds.length} flagged account(s): ${f.flaggedNeighborIds.map(label).join(', ')}.`,
      );
    }
    if (b.complaintCount === 0 && b.syntheticRisk !== 'FLAGGED') {
      observations.push('No prior complaints on record.');
    }
  }
  return {
    node,
    observations,
    connections,
    disclaimer: 'Simulated intelligence. Connections indicate association, not proof of wrongdoing.',
  };
}
