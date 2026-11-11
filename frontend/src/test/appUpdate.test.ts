import { describe, expect, it } from 'vitest';
import { appVersion, isNewer } from '@/components/common/UpdateButton';

describe('phone app update button', () => {
  it('reads the app version only from the Unifierr app', () => {
    expect(appVersion('Mozilla/5.0 (Linux; Android 15) Chrome/140 UnifierrApp/0.1.5')).toBe('0.1.5');
    expect(appVersion('Mozilla/5.0 (Linux; Android 15) Chrome/140')).toBeNull();
  });

  it('compares versions number by number', () => {
    expect(isNewer('0.1.10', '0.1.9')).toBe(true);
    expect(isNewer('0.2.0', '0.1.9')).toBe(true);
    expect(isNewer('0.1.5', '0.1.5')).toBe(false);
    expect(isNewer('0.1.4', '0.1.5')).toBe(false);
  });
});
