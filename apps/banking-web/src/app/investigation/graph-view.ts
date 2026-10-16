import { ChangeDetectionStrategy, Component, DestroyRef, ElementRef, InjectionToken, computed, effect, inject, input, signal, untracked, viewChild } from '@angular/core';
import cytoscape, { CytoscapeOptions } from 'cytoscape';
import { entries } from './format';
import { LayoutMode, NODE_STYLE, edgeLabel, graphStyle, layoutOptions, nodeLabel, toElements } from './graph-style';
import { EvidenceRef, GraphEdge, GraphLabel, GraphNode, InvestigationGraph } from './investigation.models';
import { ProvenanceBadge } from './provenance-badge';

/** Extra Cytoscape options (tests pass `headless: true`). */
export const CYTOSCAPE_OPTIONS = new InjectionToken<Partial<CytoscapeOptions>>('CYTOSCAPE_OPTIONS', { providedIn: 'root', factory: () => ({}) });

type Selection = { kind: 'node'; id: string } | { kind: 'edge'; id: string };

@Component({
  selector: 'inv-graph',
  imports: [ProvenanceBadge],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './graph-view.html',
  styleUrl: './graph-view.css',
})
export class GraphView {
  readonly graph = input.required<InvestigationGraph>();
  readonly evidenceIndex = input<Map<string, EvidenceRef[]>>(new Map());
  readonly focusId = input<string | null>(null);

  private readonly host = viewChild<ElementRef<HTMLDivElement>>('canvas');
  private readonly extra = inject(CYTOSCAPE_OPTIONS);
  private cy?: cytoscape.Core;

  protected readonly layoutMode = signal<LayoutMode>('flow');
  protected readonly selection = signal<Selection | null>(null);
  protected readonly labels = Object.keys(NODE_STYLE) as GraphLabel[];
  protected readonly nodeStyle = NODE_STYLE;
  protected readonly edgeLabel = edgeLabel;
  protected readonly nodeLabel = nodeLabel;
  protected readonly entries = entries;

  protected readonly nodeById = computed(() => new Map(this.graph().nodes.map((n) => [n.id, n])));
  protected readonly highlightedCount = computed(() => this.graph().nodes.filter((n) => n.highlighted).length);

  protected readonly selectedNode = computed<GraphNode | null>(() => {
    const s = this.selection();
    return s?.kind === 'node' ? (this.nodeById().get(s.id) ?? null) : null;
  });
  protected readonly selectedEdge = computed<GraphEdge | null>(() => {
    const s = this.selection();
    return s?.kind === 'edge' ? (this.graph().edges.find((e) => e.id === s.id) ?? null) : null;
  });
  protected readonly selectedEvidence = computed<EvidenceRef[]>(() => {
    const index = this.evidenceIndex();
    const n = this.selectedNode();
    if (n) return index.get(n.id) ?? [];
    const e = this.selectedEdge();
    if (!e) return [];
    const direct = index.get(e.id) ?? [];
    const sources = new Set((index.get(e.source) ?? []).map((r) => r.evidence));
    const both = (index.get(e.target) ?? []).filter((r) => sources.has(r.evidence));
    return [...direct, ...both.filter((r) => !direct.includes(r))];
  });

  constructor() {
    effect(() => {
      const g = this.graph();
      const mode = this.layoutMode();
      const el = this.host()?.nativeElement;
      untracked(() => this.render(g, mode, el));
    });
    effect(() => {
      const id = this.focusId();
      if (id) untracked(() => this.selectNode(id, true));
    });
    inject(DestroyRef).onDestroy(() => this.cy?.destroy());
  }

  private render(g: InvestigationGraph, mode: LayoutMode, container: HTMLDivElement | undefined): void {
    this.cy?.destroy();
    this.cy = undefined;
    if (!container && !this.extra.headless) return;
    const cy = cytoscape({
      ...this.extra,
      container: container ?? null,
      elements: toElements(g),
      style: graphStyle(),
      layout: { name: 'null' },
      minZoom: 0.2,
      maxZoom: 3,
    });
    cy.layout(layoutOptions(mode) as cytoscape.LayoutOptions).run();
    cy.fit(undefined, 40);
    cy.on('tap', 'node', (ev) => this.selection.set({ kind: 'node', id: ev.target.id() }));
    cy.on('tap', 'edge', (ev) => this.selection.set({ kind: 'edge', id: ev.target.id() }));
    cy.on('tap', (ev) => {
      if (ev.target === cy) this.clearSelection();
    });
    this.cy = cy;
    const s = this.selection();
    if (s && cy.getElementById(s.id).empty()) this.selection.set(null);
  }

  selectNode(id: string, center = false): void {
    if (!this.nodeById().has(id)) return;
    this.selection.set({ kind: 'node', id });
    this.syncSelection(id, center);
  }

  selectEdge(id: string): void {
    this.selection.set({ kind: 'edge', id });
    this.syncSelection(id, false);
  }

  clearSelection(): void {
    this.selection.set(null);
    this.cy?.elements().unselect();
  }

  private syncSelection(id: string, center: boolean): void {
    if (!this.cy) return;
    this.cy.elements().unselect();
    const el = this.cy.getElementById(id);
    el.select();
    if (center && !this.extra.headless) this.cy.animate({ center: { eles: el }, duration: 200 });
  }

  protected setLayout(mode: LayoutMode): void {
    this.layoutMode.set(mode);
  }

  protected zoomBy(factor: number): void {
    const cy = this.cy;
    if (!cy) return;
    cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  }

  protected fit(): void {
    this.cy?.fit(undefined, 40);
  }

  protected onKey(ev: KeyboardEvent): void {
    const step = 60;
    const moves: Record<string, [number, number]> = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    const move = moves[ev.key];
    if (move) this.cy?.panBy({ x: move[0], y: move[1] });
    else if (ev.key === '+' || ev.key === '=') this.zoomBy(1.25);
    else if (ev.key === '-') this.zoomBy(0.8);
    else if (ev.key === '0') this.fit();
    else return;
    ev.preventDefault();
  }

  protected endpointName(id: string): string {
    const n = this.nodeById().get(id);
    return n ? `${nodeLabel(n)} (${id})` : id;
  }
}
