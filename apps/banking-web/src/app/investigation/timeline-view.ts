import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { agentName, entries, eventSeverity, formatDuration } from './format';
import type { TraceEvent } from './investigation.models';
import type { FeedMode } from './timeline-feed';

interface AgentRun {
  agentId: string;
  startedAt: string | null;
  endedAt: string | null;
  status: string;
  durationMs: number | null;
}

const MODE_LABELS: Record<FeedMode, string> = {
  idle: 'Waiting for activity',
  streaming: 'Live',
  polling: 'Live (polling)',
  done: 'Complete',
};

@Component({
  selector: 'inv-timeline',
  imports: [DatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './timeline-view.html',
  styleUrl: './timeline-view.css',
})
export class TimelineView {
  readonly events = input<TraceEvent[]>([]);
  readonly mode = input<FeedMode>('done');
  readonly error = input('');
  readonly historical = input(false);

  protected readonly ordered = computed(() => [...this.events()].sort((a, b) => a.seq - b.seq));
  protected readonly modeLabel = computed(() => MODE_LABELS[this.mode()]);
  protected readonly runs = computed<AgentRun[]>(() => {
    const byAgent = new Map<string, AgentRun>();
    for (const e of this.ordered()) {
      const run = byAgent.get(e.agentId) ?? { agentId: e.agentId, startedAt: null, endedAt: null, status: 'RUNNING', durationMs: null };
      if (e.type === 'STARTED') run.startedAt ??= e.at;
      if (e.type === 'COMPLETED' || e.type === 'FAILED') {
        run.endedAt = e.at;
        run.status = e.type === 'FAILED' && !e.status ? 'FAILED' : (e.status ?? 'OK');
        run.durationMs = e.durationMs ?? run.durationMs;
      }
      if (e.type === 'FALLBACK' && run.status === 'RUNNING') run.status = 'DEGRADED';
      byAgent.set(e.agentId, run);
    }
    return [...byAgent.values()];
  });

  protected readonly agentName = agentName;
  protected readonly entries = entries;
  protected readonly severity = eventSeverity;
  protected readonly duration = formatDuration;
}
