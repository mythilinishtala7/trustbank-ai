import type cytoscape from 'cytoscape';
import type { GraphEdge, GraphLabel, GraphNode, InvestigationGraph } from './investigation.models';

export const NODE_STYLE: Record<GraphLabel, { shape: cytoscape.Css.NodeShape; fill: string; border: string }> = {
  Customer: { shape: 'ellipse', fill: '#0b1f3a', border: '#0b1f3a' },
  Account: { shape: 'round-rectangle', fill: '#e9effc', border: '#2f5de1' },
  Transaction: { shape: 'diamond', fill: '#eef1f6', border: '#5d6b82' },
  Beneficiary: { shape: 'hexagon', fill: '#e1f1f8', border: '#1f7a9c' },
  RiskSignal: { shape: 'triangle', fill: '#faf1da', border: '#b8860b' },
};

export const PROVENANCE_EDGE_COLORS = { VERIFIED_SYNTHETIC: '#0b6b66', INFERRED: '#5b32b0' } as const;

export function nodeLabel(n: Pick<GraphNode, 'name' | 'id'>): string {
  return n.name || n.id;
}

export function edgeLabel(e: Pick<GraphEdge, 'type' | 'kind'>): string {
  return e.kind ? `${e.type} · ${e.kind}` : e.type;
}

/** Cytoscape elements for the bounded graph; edges with a missing endpoint are dropped. */
export function toElements(g: InvestigationGraph) {
  const ids = new Set(g.nodes.map((n) => n.id));
  const anyHighlight = g.nodes.some((n) => n.highlighted) || g.edges.some((e) => e.highlighted);
  const dim = (h: boolean) => (anyHighlight && !h ? ' dim' : '');
  return [
    ...g.nodes.map((n) => ({
      group: 'nodes' as const,
      data: { id: n.id, display: nodeLabel(n), nodeLabel: n.label },
      classes: (n.highlighted ? 'hl' : '') + dim(n.highlighted),
    })),
    ...g.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({
        group: 'edges' as const,
        data: { id: e.id, source: e.source, target: e.target, display: edgeLabel(e), type: e.type, provenance: e.provenance ?? 'NONE' },
        classes: (e.highlighted ? 'hl' : '') + dim(e.highlighted),
      })),
  ];
}

export function graphStyle(): cytoscape.StylesheetJson {
  const nodeRules = (Object.keys(NODE_STYLE) as GraphLabel[]).map((label) => ({
    selector: `node[nodeLabel = "${label}"]`,
    style: {
      shape: NODE_STYLE[label].shape,
      'background-color': NODE_STYLE[label].fill,
      'border-color': NODE_STYLE[label].border,
    },
  }));
  return [
    {
      selector: 'node',
      style: {
        label: 'data(display)',
        'font-size': 11,
        color: '#0b1f3a',
        'text-valign': 'bottom',
        'text-margin-y': 6,
        'text-wrap': 'ellipsis',
        'text-max-width': '120px',
        'border-width': 2,
        width: 34,
        height: 34,
      },
    },
    ...nodeRules,
    {
      selector: 'edge',
      style: {
        width: 1.6,
        'curve-style': 'bezier',
        'line-color': '#a8b3c4',
        'target-arrow-color': '#a8b3c4',
        'target-arrow-shape': 'triangle',
        label: 'data(display)',
        'font-size': 9,
        color: '#47566d',
        'text-rotation': 'autorotate',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.85,
        'text-background-padding': '2px',
      },
    },
    { selector: 'edge[provenance = "VERIFIED_SYNTHETIC"]', style: { 'line-color': PROVENANCE_EDGE_COLORS.VERIFIED_SYNTHETIC, 'target-arrow-color': PROVENANCE_EDGE_COLORS.VERIFIED_SYNTHETIC, 'line-style': 'dashed' } },
    { selector: 'edge[provenance = "INFERRED"]', style: { 'line-color': PROVENANCE_EDGE_COLORS.INFERRED, 'target-arrow-color': PROVENANCE_EDGE_COLORS.INFERRED, 'line-style': 'dotted' } },
    { selector: '.dim', style: { opacity: 0.5 } },
    { selector: 'node.hl', style: { 'border-width': 4, 'underlay-color': '#2f5de1', 'underlay-opacity': 0.28, 'underlay-padding': 8 } },
    { selector: 'edge.hl', style: { width: 4, 'underlay-color': '#2f5de1', 'underlay-opacity': 0.28, 'underlay-padding': 4 } },
    { selector: ':selected', style: { 'border-color': '#0b1f3a', 'border-width': 4, 'overlay-color': '#0b1f3a', 'overlay-opacity': 0.12 } },
  ];
}

export type LayoutMode = 'flow' | 'cluster';

export function layoutOptions(mode: LayoutMode) {
  return mode === 'flow'
    ? { name: 'breadthfirst', directed: true, spacingFactor: 1.25, padding: 30, animate: false }
    : { name: 'cose', animate: false, randomize: true, padding: 30, nodeRepulsion: () => 250000, idealEdgeLength: () => 150, numIter: 1500 };
}
