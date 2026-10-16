import { Component, input, output } from '@angular/core';
import type { ApiError } from '../../core/models';

@Component({
  selector: 'app-error-panel',
  template: `
    <div class="banner neutral" role="alert">
      <h2>{{ error().kind === 'unavailable' ? 'Service temporarily unavailable' : error().kind === 'network' ? 'Connection problem' : 'Something went wrong' }}</h2>
      <p>{{ error().message }}</p>
      @if (error().requestId) {
        <p class="muted small">Reference: {{ error().requestId }}</p>
      }
      @if (retryable()) {
        <button type="button" class="btn secondary inline" (click)="retry.emit()">Try again</button>
      }
    </div>
  `,
})
export class ErrorPanel {
  readonly error = input.required<ApiError>();
  readonly retryable = input(true);
  readonly retry = output();
}
