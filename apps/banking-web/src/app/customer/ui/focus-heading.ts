import { Directive, ElementRef, Injector, afterNextRender, effect, inject, input } from '@angular/core';

/** Moves keyboard/screen-reader focus to the heading on first render and whenever the bound key changes. */
@Directive({
  selector: '[appFocusHeading]',
  host: { tabindex: '-1' },
})
export class FocusHeading {
  readonly key = input<unknown>(undefined, { alias: 'appFocusHeading' });
  private el = inject<ElementRef<HTMLElement>>(ElementRef);
  private injector = inject(Injector);

  constructor() {
    effect(() => {
      this.key();
      afterNextRender(() => this.el.nativeElement.focus({ preventScroll: false }), { injector: this.injector });
    });
  }
}
