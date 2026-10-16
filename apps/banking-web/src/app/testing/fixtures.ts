import type { CustomerPayment, Me, Question } from '../core/models';

export const NOW = Date.parse('2026-01-01T10:00:00Z');

export function payment(over: Partial<CustomerPayment> = {}): CustomerPayment {
  return {
    id: 'txn_ab12cd34',
    status: 'READY_FOR_AUTH',
    recipient: { displayName: 'Rahul Verma', handle: 'rahul.verma@trustpay', verified: true },
    amount: 2500,
    note: 'Dinner',
    createdAt: '2026-01-01T09:59:00Z',
    serverTime: new Date(NOW).toISOString(),
    explanation: null,
    reasons: [],
    questions: [],
    holdUntil: null,
    verified: false,
    actions: ['AUTHORIZE', 'CANCEL'],
    simulated: true,
    ...over,
  };
}

export const QUESTIONS: Question[] = [
  {
    id: 'source_of_details',
    text: 'How did you get these payment details?',
    allowFreeText: true,
    options: [
      { value: 'friend_family', label: 'From a friend or family member' },
      { value: 'online_job_site', label: 'From an online job site' },
    ],
  },
  { id: 'promised_benefit', text: 'Were you promised a benefit?', allowFreeText: false, options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
  { id: 'urgency_or_secrecy', text: 'Were you asked to hurry or keep it secret?', allowFreeText: false, options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
  { id: 'recipient_relationship', text: 'Fourth question that must not render', allowFreeText: false, options: [{ value: 'never_met', label: 'Never met' }] },
];

export const ME: Me = {
  displayName: 'Asha Menon',
  handle: 'asha.menon@trustpay',
  balance: 125000,
  recentTransactions: [{ id: 'txn_hist_1', recipientName: 'Greenleaf Bakery', amount: 450, note: 'Bread', timestamp: '2025-12-30T08:00:00Z' }],
};

export const STATUS_FIXTURES: CustomerPayment[] = [
  payment({ status: 'ASSESSING', actions: ['CANCEL'] }),
  payment({ status: 'QUESTIONNAIRE', questions: QUESTIONS, actions: ['ANSWER', 'CANCEL'], explanation: 'A few details need confirming.' }),
  payment({ status: 'REVIEW', explanation: 'This recipient is new to you.', reasons: ['First payment to this recipient'], actions: ['ACKNOWLEDGE', 'CANCEL'] }),
  payment({
    status: 'HOLD_ACTIVE',
    explanation: 'We paused this payment to give you time to check.',
    reasons: ['Several people paid this recipient recently'],
    holdUntil: new Date(NOW + 180_000).toISOString(),
    actions: ['CANCEL'],
  }),
  payment({ status: 'HOLD_EXPIRED', explanation: 'The pause has ended.', reasons: ['Recipient is new'], holdUntil: new Date(NOW - 1000).toISOString(), actions: ['VERIFY', 'CANCEL'] }),
  payment({ status: 'READY_FOR_AUTH' }),
  payment({ status: 'COMPLETED', actions: [] }),
  payment({ status: 'CANCELLED', actions: [] }),
];
