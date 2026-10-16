import { Component, input } from '@angular/core';
import type { CustomerPayment } from '../../core/models';

@Component({
  selector: 'app-explanation',
  template: `
    <section class="banner" [class.caution]="tone() === 'caution'" [class.high]="tone() === 'high'" [class.neutral]="tone() === 'neutral'" [attr.aria-labelledby]="'why-title'">
      <h2 id="why-title">{{ heading() }}</h2>
      @if (payment().explanation) {
        <p>{{ payment().explanation }}</p>
      }
      @if (payment().reasons.length) {
        <ul class="reasons">
          @for (r of payment().reasons; track $index) {
            <li>{{ r }}</li>
          }
        </ul>
      }
    </section>
  `,
  styles: `
    .reasons { margin: 8px 0 0; padding-left: 20px; font-size: 14px; }
    .reasons li { margin-bottom: 4px; }
  `,
})
export class Explanation {
  readonly payment = input.required<CustomerPayment>();
  readonly heading = input.required<string>();
  readonly tone = input<'neutral' | 'caution' | 'high'>('caution');
}
