import type { Beneficiary, CustomerProfile, Scenario, Transaction, TransactionStatus } from './models';

export const CUSTOMER_ID = 'cust_asha';

export interface Transfer {
  id: string;
  from: string;
  to: string;
  amount: number;
  timestamp: string;
  status: TransactionStatus;
}

export type Clock = () => Date;

const HOUR = 3600_000;
const DAY = 24 * HOUR;

/** Mutable in-memory store seeded with deterministic synthetic data. */
export class Store {
  customers = new Map<string, CustomerProfile>();
  beneficiaries = new Map<string, Beneficiary>();
  transactions: Transaction[] = [];
  /** Synthetic transfers between non-demo-customer entities (victims, mules). */
  networkTransfers: Transfer[] = [];
  customerNames = new Map<string, string>();

  constructor(readonly clock: Clock) {}

  ago(ms: number): string {
    return new Date(this.clock().getTime() - ms).toISOString();
  }

  addTransaction(t: Transaction): void {
    this.transactions.unshift(t);
  }

  transfers(): Transfer[] {
    const own: Transfer[] = this.transactions
      .filter((t) => t.status === 'COMPLETED')
      .map((t) => ({
        id: t.id,
        from: t.customerId,
        to: t.beneficiaryId,
        amount: t.amount,
        timestamp: t.timestamp,
        status: t.status,
      }));
    return [...own, ...this.networkTransfers];
  }
}

function beneficiary(
  id: string,
  displayName: string,
  handle: string,
  bankLabel: string,
  ageMs: number,
  now: Date,
  extra: Partial<Beneficiary> = {},
): Beneficiary {
  return {
    id,
    displayName,
    handle,
    maskedAccount: `XXXXXX${String(1000 + ([...id].reduce((a, c) => a * 31 + c.charCodeAt(0), 7) % 9000))}`,
    bankLabel,
    firstSeenAt: new Date(now.getTime() - ageMs).toISOString(),
    complaintCount: 0,
    ...extra,
  };
}

export function createSeededStore(clock: Clock): Store {
  const store = new Store(clock);
  const now = clock();
  const ago = (ms: number) => store.ago(ms);

  store.customers.set(CUSTOMER_ID, {
    id: CUSTOMER_ID,
    displayName: 'Asha Menon',
    upiHandle: 'asha.menon@trustpay',
    balance: 84_250,
  });
  store.customerNames.set(CUSTOMER_ID, 'Asha Menon');
  for (const [id, name] of [
    ['cust_karan', 'Karan S.'],
    ['cust_meera', 'Meera P.'],
    ['cust_imran', 'Imran K.'],
    ['cust_divya', 'Divya R.'],
  ] as const) {
    store.customerNames.set(id, name);
    store.customers.set(id, { id, displayName: name, upiHandle: `${id.slice(5)}@trustpay`, balance: 0 });
  }

  const list: Beneficiary[] = [
    beneficiary('ben_rahul', 'Rahul Verma', 'rahul.verma@trustpay', 'Demo Bank', 400 * DAY, now),
    beneficiary('ben_freshmart', 'Fresh Mart Grocers', 'freshmart@trustpay', 'Demo Bank', 300 * DAY, now),
    beneficiary('ben_citypower', 'City Power Board', 'citypower@trustpay', 'Demo Bank', 500 * DAY, now),
    beneficiary('ben_metrocafe', 'Metro Cafe', 'metrocafe@trustpay', 'Demo Bank', 200 * DAY, now),
    beneficiary('ben_novatrade', 'Nova Trade Desk', 'nova.trade@trustpay', 'Demo Bank', 3 * DAY, now),
    beneficiary('ben_mule_a', 'Swift Assist Services', 'swift.assist@trustpay', 'Demo Bank', 9 * DAY, now, {
      syntheticRisk: 'FLAGGED',
      complaintCount: 5,
    }),
    beneficiary('ben_mule_b', 'Quick Returns Hub', 'quick.returns@trustpay', 'Demo Bank', 6 * DAY, now, {
      syntheticRisk: 'FLAGGED',
      complaintCount: 3,
    }),
    beneficiary('ben_mule_c', 'Task Rewards Desk', 'task.rewards@trustpay', 'Demo Bank', 11 * DAY, now, {
      syntheticRisk: 'FLAGGED',
      complaintCount: 4,
    }),
  ];
  list.forEach((b) => store.beneficiaries.set(b.id, b));

  // Asha's history: rent 2,500 monthly plus small everyday payments.
  const hist: [string, number, string, number][] = [
    ['ben_rahul', 2500, 'September rent', 43],
    ['ben_rahul', 2500, 'August rent', 74],
    ['ben_rahul', 2500, 'July rent', 104],
    ['ben_freshmart', 1850, 'Groceries', 5],
    ['ben_freshmart', 1240, 'Groceries', 19],
    ['ben_freshmart', 2100, 'Groceries', 33],
    ['ben_citypower', 1960, 'Electricity bill', 12],
    ['ben_metrocafe', 480, 'Lunch', 2],
    ['ben_metrocafe', 360, 'Coffee', 9],
  ];
  hist.forEach(([bid, amount, note, days], i) =>
    store.transactions.push({
      id: `txn_hist_${i + 1}`,
      customerId: CUSTOMER_ID,
      beneficiaryId: bid,
      amount,
      currency: 'INR',
      note,
      timestamp: ago(days * DAY),
      status: 'COMPLETED',
    }),
  );
  store.transactions.sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  // Synthetic network around ben_novatrade (no complaints of its own).
  const t = (id: string, from: string, to: string, amount: number, hours: number): Transfer => ({
    id,
    from,
    to,
    amount,
    timestamp: ago(hours * HOUR),
    status: 'COMPLETED',
  });
  store.networkTransfers = [
    t('net_1', 'cust_karan', 'ben_novatrade', 8000, 40),
    t('net_2', 'cust_meera', 'ben_novatrade', 12000, 26),
    t('net_3', 'cust_imran', 'ben_novatrade', 5000, 4),
    t('net_4', 'ben_mule_a', 'ben_novatrade', 15000, 30),
    t('net_5', 'ben_novatrade', 'ben_mule_b', 20000, 3),
    t('net_6', 'cust_divya', 'ben_mule_a', 9000, 52),
    t('net_7', 'cust_meera', 'ben_mule_c', 6500, 60),
    t('net_8', 'ben_mule_c', 'ben_mule_b', 6000, 58),
    t('net_9', 'cust_karan', 'ben_mule_b', 4000, 70),
  ];

  return store;
}

export const SCENARIOS: Scenario[] = [
  {
    id: 'scenario_a_rent',
    title: 'A · Routine rent payment',
    description: '₹2,500 to a known landlord. Matches Asha’s usual activity.',
    handle: 'rahul.verma@trustpay',
    amount: 2500,
    note: 'October rent',
    expectedOutcome: 'LOW → goes straight to PIN, no questions.',
  },
  {
    id: 'scenario_b_new_account',
    title: 'B · New recipient, linked network',
    description: '₹25,000 to a 3-day-old handle with no complaints but links to flagged accounts.',
    handle: 'nova.trade@trustpay',
    amount: 25000,
    note: 'Account activation fee',
    expectedOutcome: 'MEDIUM → scam check. Answer “Friend/Family” + “No” to see REVIEW.',
    suggestedAnswers: { sourceOfDetails: 'FRIEND_FAMILY', promisedBenefit: 'NO' },
  },
  {
    id: 'scenario_c_scam',
    title: 'C · High-confidence scam interception',
    description: 'Same payment as B; details came via Telegram and task payouts were promised.',
    handle: 'nova.trade@trustpay',
    amount: 25000,
    note: 'Task deposit',
    expectedOutcome: 'HIGH → PIN blocked, 120-second simulated cooling-off hold.',
    suggestedAnswers: { sourceOfDetails: 'MESSAGING_APP', promisedBenefit: 'YES' },
  },
];
