import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { Gate } from './gate';
import { InvestigatorSession } from './investigator-session';
import { SearchPage } from './search-page';

/** `/investigation`: the access-code gate until a valid investigator token exists, then transaction search. */
@Component({
  selector: 'inv-landing',
  imports: [Gate, SearchPage],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (session.authenticated()) {
      <inv-search-page />
    } @else {
      <inv-gate />
    }
  `,
})
export class Landing {
  protected readonly session = inject(InvestigatorSession);
}
