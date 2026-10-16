export const NOTE_MAX = 80;
export const FREE_TEXT_MAX = 300;

const UPI_ID = /^[A-Za-z0-9._-]{2,64}@[A-Za-z][A-Za-z0-9]{1,63}$/;
const ACCOUNT_NUMBER = /^\d{9,18}$/;

export function isUpiId(v: string): boolean {
  return UPI_ID.test(v);
}

export function isAccountNumber(v: string): boolean {
  return ACCOUNT_NUMBER.test(v);
}

export function recipientError(raw: string): string {
  const v = raw.trim();
  if (!v) return 'Enter a UPI ID or an account number.';
  if (v.includes('@')) return isUpiId(v) ? '' : 'Enter a valid UPI ID, for example name@bank.';
  if (/^\d+$/.test(v)) return isAccountNumber(v) ? '' : 'An account number has 9 to 18 digits.';
  return 'Enter a UPI ID (name@bank) or an account number of 9 to 18 digits.';
}

export function amountError(value: number | null): string {
  if (value === null || Number.isNaN(value)) return 'Enter an amount.';
  if (!Number.isInteger(value)) return 'Enter a whole number of rupees.';
  if (value < 1) return 'Amount must be at least ₹1.';
  return '';
}

export function pinError(pin: string): string {
  return /^\d{4,6}$/.test(pin) ? '' : 'Enter a PIN of 4 to 6 digits.';
}
