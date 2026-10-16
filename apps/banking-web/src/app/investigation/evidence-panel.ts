import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { agentName, entries, formatDuration } from './format';
import type { Assessment, Evidence, Finding, Question } from './investigation.models';
import { ProvenanceBadge } from './provenance-badge';

interface FindingView {
  finding: Finding;
  contributing: Evidence[];
  context: Evidence[];
}

@Component({
  selector: 'inv-evidence-panel',
  imports: [DatePipe, NgTemplateOutlet, ProvenanceBadge],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './evidence-panel.html',
  styleUrl: './evidence-panel.css',
})
export class EvidencePanel {
  readonly assessments = input<Assessment[]>([]);
  readonly historical = input(false);
  readonly entitySelected = output<string>();

  private readonly chosen = signal<string | null>(null);

  protected readonly current = computed<Assessment | null>(() => {
    const list = this.assessments();
    return list.find((a) => a.id === this.chosen()) ?? list.find((a) => a.stage === 'FINAL') ?? list[list.length - 1] ?? null;
  });

  protected readonly views = computed<FindingView[]>(() =>
    (this.current()?.findings ?? []).map((finding) => ({
      finding,
      contributing: finding.evidence.filter((e) => e.points > 0),
      context: finding.evidence.filter((e) => e.points <= 0),
    })),
  );

  protected readonly noContributingEvidence = computed(() => this.views().every((v) => v.contributing.length === 0));

  protected readonly weighted = computed(() => {
    const a = this.current();
    if (!a) return null;
    return {
      anomaly: Math.round(a.aggregate.anomalyScore * a.config.anomalyWeight * 10) / 10,
      network: Math.round(a.aggregate.networkScore * a.config.networkWeight * 10) / 10,
    };
  });

  protected readonly agentName = agentName;
  protected readonly duration = formatDuration;
  protected readonly entries = entries;

  protected choose(id: string): void {
    this.chosen.set(id);
  }

  protected isCurrent(a: Assessment): boolean {
    return this.current()?.id === a.id;
  }

  protected optionLabel(q: Question | undefined, value: string): string {
    return q?.options.find((o) => o.value === value)?.label ?? value;
  }

  protected question(a: Assessment, id: string): Question | undefined {
    return a.questions.find((q) => q.id === id);
  }
}
