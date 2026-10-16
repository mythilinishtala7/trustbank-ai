import { Component, computed, input, output, signal } from '@angular/core';
import type { Answer, CustomerPayment } from '../../core/models';
import { FREE_TEXT_MAX } from './validation';

const MAX_QUESTIONS = 3;

@Component({
  selector: 'app-questionnaire',
  template: `
    <p class="muted">Some payments need an extra check. Your answers help us protect you and are used only for this payment.</p>
    <form (submit)="$event.preventDefault(); submit()" novalidate>
      @for (q of questions(); track q.id) {
        <fieldset class="card">
          <legend>{{ q.text }}</legend>
          @for (o of q.options; track o.value) {
            <label class="radio">
              <input type="radio" [name]="q.id" [value]="o.value" [checked]="selected()[q.id] === o.value" (change)="select(q.id, o.value)" />
              {{ o.label }}
            </label>
          }
          @if (q.allowFreeText) {
            <label [for]="'ft-' + q.id">Anything you'd like to add? (optional)</label>
            <textarea
              [id]="'ft-' + q.id" rows="3" [maxLength]="freeTextMax" [value]="texts()[q.id] ?? ''"
              (input)="setText(q.id, $any($event.target).value)" [attr.aria-describedby]="'ftc-' + q.id"
            ></textarea>
            <p [id]="'ftc-' + q.id" class="muted small counter">{{ (texts()[q.id] ?? '').length }}/{{ freeTextMax }}</p>
          }
        </fieldset>
      }
      <button type="submit" class="btn" [disabled]="busy() || !complete()">{{ busy() ? 'Submitting…' : 'Continue' }}</button>
    </form>
  `,
  styles: `
    .counter { margin: 4px 0 0; text-align: right; }
    fieldset.card { margin-bottom: 12px; }
    textarea { width: 100%; padding: 12px; font: inherit; border: 1px solid var(--line); border-radius: 12px; resize: vertical; color: var(--navy); }
    textarea:focus-visible { outline: 3px solid rgba(47, 93, 225, 0.35); outline-offset: 1px; border-color: var(--blue); }
  `,
})
export class Questionnaire {
  readonly payment = input.required<CustomerPayment>();
  readonly busy = input(false);
  readonly answered = output<Answer[]>();

  readonly freeTextMax = FREE_TEXT_MAX;
  readonly selected = signal<Record<string, string>>({});
  readonly texts = signal<Record<string, string>>({});

  readonly questions = computed(() => this.payment().questions.slice(0, MAX_QUESTIONS));
  readonly complete = computed(() => this.questions().length > 0 && this.questions().every((q) => !!this.selected()[q.id]));

  select(id: string, value: string): void {
    this.selected.update((s) => ({ ...s, [id]: value }));
  }

  setText(id: string, value: string): void {
    this.texts.update((t) => ({ ...t, [id]: value.slice(0, FREE_TEXT_MAX) }));
  }

  submit(): void {
    if (!this.complete() || this.busy()) return;
    const answers = this.questions().map((q): Answer => {
      const text = q.allowFreeText ? (this.texts()[q.id] ?? '').trim() : '';
      return { questionId: q.id, option: this.selected()[q.id], ...(text ? { freeText: text } : {}) };
    });
    this.answered.emit(answers);
  }
}
