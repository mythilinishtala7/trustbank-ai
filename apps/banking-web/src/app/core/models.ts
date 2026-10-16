// Hand-written mirror of the customer part of the frozen API contract (camelCase JSON).
// Customer models intentionally contain no scores, agent names, graph data, traces or evidence ids.

export interface Persona {
  id: string;
  displayName: string;
  handle: string;
  blurb: string;
}

export interface AuthResponse {
  token: string;
  role: 'customer';
  expiresAt: string;
  displayName: string;
}

export interface RecentTransaction {
  id: string;
  recipientName: string;
  amount: number;
  note: string;
  timestamp: string;
}

export interface Me {
  displayName: string;
  handle: string;
  balance: number;
  recentTransactions: RecentTransaction[];
}

export interface RecipientLookup {
  found: boolean;
  verified: boolean;
  displayName: string | null;
  handle: string;
  maskedAccount: string | null;
}

export type PaymentStatus =
  | 'INITIATED'
  | 'ASSESSING'
  | 'QUESTIONNAIRE'
  | 'REVIEW'
  | 'HOLD_ACTIVE'
  | 'HOLD_EXPIRED'
  | 'READY_FOR_AUTH'
  | 'COMPLETED'
  | 'CANCELLED';

export type PaymentAction = 'ANSWER' | 'ACKNOWLEDGE' | 'VERIFY' | 'CONTINUE' | 'AUTHORIZE' | 'CANCEL';

export interface Option {
  value: string;
  label: string;
}

export interface Question {
  id: string;
  text: string;
  options: Option[];
  allowFreeText: boolean;
}

export interface Answer {
  questionId: string;
  option: string;
  freeText?: string;
}

export interface PaymentRecipient {
  displayName: string | null;
  handle: string;
  verified: boolean;
}

export interface CustomerPayment {
  id: string;
  status: PaymentStatus;
  recipient: PaymentRecipient;
  amount: number;
  note: string;
  createdAt: string;
  serverTime: string;
  explanation: string | null;
  reasons: string[];
  questions: Question[];
  holdUntil: string | null;
  verified: boolean;
  actions: PaymentAction[];
  simulated: boolean;
}

export interface CreatePaymentRequest {
  recipient: string;
  amount: number;
  note?: string;
}

export type ApiErrorKind = 'network' | 'unavailable' | 'unauthenticated' | 'validation' | 'conflict' | 'notFound' | 'other';

export interface ApiError {
  kind: ApiErrorKind;
  status: number;
  code: string;
  message: string;
  requestId?: string;
}
