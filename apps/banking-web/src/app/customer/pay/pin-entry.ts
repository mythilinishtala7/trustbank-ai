import { Component, input, output, signal } from '@angular/core';
import { pinError } from './validation';

@Component({
  selector: 'app-pin-entry',
  template: `
    <form class="card" (submit)="$event.preventDefault(); submit()" novalidate>
      <p class="muted">This is a demo PIN screen. Enter any 4 to 6 digits. Never enter a real PIN.</p>
      <label for="pin">Demo PIN</label>
      <input
        id="pin" type="password" inputmode="numeric" autocomplete="off" maxlength="6"
        [value]="pin()" (input)="onInput($event)"
        [attr.aria-invalid]="touched() && invalid() ? 'true' : null" aria-describedby="pin-error"
      />
      <p id="pin-error" class="error" [hidden]="!(touched() && invalid())" role="alert">{{ message() }}</p>
      <button type="submit" class="btn" [disabled]="busy()">{{ busy() ? 'Authorizing…' : 'Authorize payment' }}</button>
    </form>
  `,
})
export class PinEntry {
  readonly busy = input(false);
  readonly authorized = output<string>();

  readonly pin = signal('');
  readonly touched = signal(false);

  invalid(): boolean {
    return !!pinError(this.pin());
  }

  message(): string {
    return pinError(this.pin());
  }

  onInput(event: Event): void {
    const el = event.target as HTMLInputElement;
    const digits = el.value.replace(/\D/g, '').slice(0, 6);
    el.value = digits;
    this.pin.set(digits);
  }

  submit(): void {
    this.touched.set(true);
    if (this.invalid() || this.busy()) return;
    const value = this.pin();
    this.pin.set('');
    this.touched.set(false);
    this.authorized.emit(value);
  }
}
