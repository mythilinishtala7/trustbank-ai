import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, ElementRef, OnDestroy, OnInit, inject, signal, viewChild } from '@angular/core';
import cytoscape from 'cytoscape';
import { ApiService, errorMessage } from '../api.service';
import type { GraphEdge, GraphResponse, NodeDetail, Payment } from '../models';

const COLORS = {
  NORMAL: { bg: '#e8efff', border: '#2864e8' },
  WATCH: { bg: '#fdf3dc', border: '#d99116' },
  FLAGGED: { bg: '#fdeceb', border: '#d92d20' },
} as const;

@Component({
  selector: 'app-investigator',
  imports: [CurrencyPipe, DatePipe],
  templateUrl: './investigator.html',
})
export class Investigator implements OnInit, OnDestroy {
  private api = inject(ApiService);
  private host = viewChild.required<ElementRef<HTMLDivElement>>('canvas');
  private cy?: cytoscape.Core;

  graph = signal<GraphResponse | null>(null);
  detail = signal<NodeDetail | null>(null);
  edge = signal<GraphEdge | null>(null);
  payments = signal<Payment[]>([]);
  error = signal('');

  ngOnInit(): void {
    this.api.payments().subscribe({ next: (p) => this.payments.set(p), error: () => undefined });
    this.api.graph().subscribe({
      next: (g) => {
        this.graph.set(g);
        queueMicrotask(() => this.render(g));
      },
      error: (e) => this.error.set(errorMessage(e)),
    });
  }

  ngOnDestroy(): void {
    this.cy?.destroy();
  }

  count(level: 'FLAGGED' | 'WATCH'): number {
    return this.graph()?.nodes.filter((n) => n.riskLevel === level).length ?? 0;
  }

  private render(g: GraphResponse): void {
    this.cy = cytoscape({
      container: this.host().nativeElement,
      elements: [
        ...g.nodes.map((n) => ({ data: { id: n.id, label: n.label, type: n.type, risk: n.riskLevel } })),
        ...g.edges.map((e) => ({ data: { id: e.id, source: e.source, target: e.target } })),
      ],
      layout: {
        name: 'cose',
        animate: false,
        randomize: true,
        fit: true,
        padding: 40,
        nodeRepulsion: () => 250000,
        nodeOverlap: 30,
        idealEdgeLength: () => 170,
        numIter: 3000,
      },
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'font-size': 11,
            color: '#14243a',
            'text-valign': 'bottom',
            'text-margin-y': 6,
            'background-color': COLORS.NORMAL.bg,
            'border-color': COLORS.NORMAL.border,
            'border-width': 2,
            width: 30,
            height: 30,
          },
        },
        { selector: 'node[type = "beneficiary"]', style: { shape: 'round-rectangle' } },
        { selector: 'node[type = "customer"]', style: { shape: 'ellipse', 'background-color': '#ffffff', 'border-color': '#14243a' } },
        { selector: 'node[risk = "WATCH"]', style: { 'background-color': COLORS.WATCH.bg, 'border-color': COLORS.WATCH.border } },
        { selector: 'node[risk = "FLAGGED"]', style: { 'background-color': COLORS.FLAGGED.bg, 'border-color': COLORS.FLAGGED.border } },
        {
          selector: 'edge',
          style: {
            width: 1.5,
            'line-color': '#b6c0cf',
            'target-arrow-color': '#b6c0cf',
            'target-arrow-shape': 'triangle',
            'curve-style': 'bezier',
          },
        },
        { selector: '.highlight', style: { 'border-width': 4, 'line-color': '#2864e8', 'target-arrow-color': '#2864e8' } },
        { selector: ':selected', style: { 'overlay-color': '#2864e8', 'overlay-opacity': 0.15 } },
      ],
    });
    this.cy.on('tap', 'node', (ev) => this.selectNode(ev.target.id()));
    this.cy.on('tap', 'edge', (ev) => {
      const e = this.graph()?.edges.find((x) => x.id === ev.target.id()) ?? null;
      this.detail.set(null);
      this.edge.set(e);
    });
  }

  selectNode(id: string): void {
    this.edge.set(null);
    this.api.nodeDetail(id).subscribe({ next: (d) => this.detail.set(d), error: (e) => this.error.set(errorMessage(e)) });
  }

  highlight(p: Payment): void {
    if (!this.cy) return;
    this.cy.elements().removeClass('highlight');
    const ids = new Set(p.assessment.graphEntityIds);
    const nodes = this.cy.nodes().filter((n) => ids.has(n.id()));
    nodes.addClass('highlight');
    nodes.edgesWith(nodes).addClass('highlight');
    this.cy.animate({ fit: { eles: nodes, padding: 60 }, duration: 250 });
  }

  fit(): void { this.cy?.fit(undefined, 40); }
  zoom(f: number): void { this.cy?.zoom({ level: this.cy.zoom() * f, renderedPosition: { x: this.cy.width() / 2, y: this.cy.height() / 2 } }); }
}
