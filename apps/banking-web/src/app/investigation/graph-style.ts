import type cytoscape from 'cytoscape';
import type { GraphEdge, GraphLabel, GraphNode, InvestigationGraph } from './investigation.models';

export const NODE_STYLE: Record<GraphLabel, { shape: cytoscape.Css.NodeShape; fill: string; border: string }> = {
  Customer: { shape: 'ellipse', fill: '#31446b', border: '#93a2ba' },
  Account: { shape: 'round-rectangle', fill: '#1a2c4e', border: '#4d7cfe' },
  Transaction: { shape: 'diamond', fill: '#1c2438', border: '#93a2ba' },
  Beneficiary: { shape: 'hexagon', fill: '#12303f', border: '#4db3d9' },
  RiskSignal: { shape: 'triangle', fill: '#2e2510', border: '#e0a83f' },
};

export const PROVENANCE_EDGE_COLORS = { VERIFIED_SYNTHETIC: '#5fd4cb', INFERRED: '#b79cf0' } as const;

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
        color: '#e9eff8',
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
        'line-color': '#3d4f74',
        'target-arrow-color': '#3d4f74',
        'target-arrow-shape': 'triangle',
        label: 'data(display)',
        'font-size': 9,
        color: '#93a2ba',
        'text-rotation': 'autorotate',
        'text-background-color': '#0a1220',
        'text-background-opacity': 0.85,
        'text-background-padding': '2px',
      },
    },
    { selector: 'edge[provenance = "VERIFIED_SYNTHETIC"]', style: { 'line-color': PROVENANCE_EDGE_COLORS.VERIFIED_SYNTHETIC, 'target-arrow-color': PROVENANCE_EDGE_COLORS.VERIFIED_SYNTHETIC, 'line-style': 'dashed' } },
    { selector: 'edge[provenance = "INFERRED"]', style: { 'line-color': PROVENANCE_EDGE_COLORS.INFERRED, 'target-arrow-color': PROVENANCE_EDGE_COLORS.INFERRED, 'line-style': 'dotted' } },
    { selector: '.dim', style: { opacity: 0.5 } },
    { selector: 'node.hl', style: { 'border-width': 4, 'underlay-color': '#4d7cfe', 'underlay-opacity': 0.28, 'underlay-padding': 8 } },
    { selector: 'edge.hl', style: { width: 4, 'underlay-color': '#4d7cfe', 'underlay-opacity': 0.28, 'underlay-padding': 4 } },
    { selector: ':selected', style: { 'border-color': '#e9eff8', 'border-width': 4, 'overlay-color': '#e9eff8', 'overlay-opacity': 0.12 } },
  ];
}

export type LayoutMode = 'flow' | 'cluster';

export function layoutOptions(mode: LayoutMode) {
  return mode === 'flow'
    ? { name: 'breadthfirst', directed: true, spacingFactor: 1.25, padding: 30, animate: false }
    : { name: 'cose', animate: false, randomize: true, padding: 30, nodeRepulsion: () => 250000, idealEdgeLength: () => 150, numIter: 1500 };
}
