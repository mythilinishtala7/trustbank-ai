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
    .prov-verified_synthetic { color: #0b6b66; background: #e0f4f2; border-color: #9fd6d1; }
    .prov-inferred { color: #5b32b0; background: #efe9fb; border-color: #c9b6ee; border-style: dashed; }
    .prov-user_provided { color: #8a4600; background: #fff0dc; border-color: #f0c78f; }
  `,
})
export class ProvenanceBadge {
  readonly value = input<Provenance | null | undefined>();
  protected readonly meta = computed(() => {
    const v = this.value();
    return v ? PROVENANCE_LABELS[v] : null;
  });
}
