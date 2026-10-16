import { amountError, isAccountNumber, isUpiId, pinError, recipientError } from './validation';

describe('validation', () => {
  it('accepts UPI ids and 9-18 digit account numbers only', () => {
    expect(isUpiId('rahul.verma@trustpay')).toBe(true);
    expect(isUpiId('rahul verma@trustpay')).toBe(false);
    expect(isUpiId('@trustpay')).toBe(false);
    expect(isAccountNumber('123456789')).toBe(true);
    expect(isAccountNumber('123456789012345678')).toBe(true);
    expect(isAccountNumber('12345678')).toBe(false);
    expect(isAccountNumber('1234567890123456789')).toBe(false);
    expect(recipientError('12345')).toMatch(/9 to 18 digits/);
    expect(recipientError('  ')).toMatch(/Enter/);
    expect(recipientError('name@bank')).toBe('');
    expect(recipientError('hello')).not.toBe('');
  });

  it('validates amount and pin', () => {
    expect(amountError(null)).not.toBe('');
    expect(amountError(0)).not.toBe('');
    expect(amountError(10.5)).not.toBe('');
    expect(amountError(10)).toBe('');
    expect(pinError('123')).not.toBe('');
    expect(pinError('1234')).toBe('');
    expect(pinError('123456')).toBe('');
    expect(pinError('1234567')).not.toBe('');
  });
});
