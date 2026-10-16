import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { PROVENANCE_LABELS, Provenance } from './investigation.models';

@Component({
  selector: 'inv-prov',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (meta(); as m) {
      <span [class]="'prov prov-' + value()!.toLowerCase()" [attr.data-provenance]="value()" [title]="m.hint">
        <span aria-hidden="true">{{ m.glyph }}</span> {{ m.label }}
      </span>
    }
  `,
  styles: `
    .prov { display: inline-flex; gap: 4px; align-items: center; font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px; border: 1px solid; white-space: nowrap; }
    .prov-verified_synthetic { color: #5fd4cb; background: rgba(95, 212, 203, 0.12); border-color: rgba(95, 212, 203, 0.4); }
    .prov-inferred { color: #b79cf0; background: rgba(183, 156, 240, 0.12); border-color: rgba(183, 156, 240, 0.4); border-style: dashed; }
    .prov-user_provided { color: #f0a95e; background: rgba(240, 169, 94, 0.12); border-color: rgba(240, 169, 94, 0.4); }
  `,
})
export class ProvenanceBadge {
  readonly value = input<Provenance | null | undefined>();
  protected readonly meta = computed(() => {
    const v = this.value();
    return v ? PROVENANCE_LABELS[v] : null;
  });
}
