import { describe, it, expect } from 'vitest';
import {
  formatState,
  formatTime,
  formatSessionId,
  getStatusDotClass
} from '../formatters';

describe('formatState', () => {
  it('returns empty string for undefined', () => {
    expect(formatState(undefined)).toBe('');
  });

  it('maps known states to labels', () => {
    expect(formatState('CREATED')).toBe('Ready');
    expect(formatState('RUNNING')).toBe('Running');
    expect(formatState('AWAITING_INPUT')).toBe('Awaiting input');
    expect(formatState('INTERRUPTING')).toBe('Interrupting');
    expect(formatState('ERROR')).toBe('Error');
  });

  it('formats unknown states by lowercasing and replacing underscores', () => {
    expect(formatState('SOME_UNKNOWN_STATE')).toBe('some unknown state');
  });
});

describe('formatTime', () => {
  it('returns "just now" for timestamps less than a minute ago', () => {
    const now = new Date().toISOString();
    expect(formatTime(now)).toBe('just now');
  });

  it('returns minutes ago for recent timestamps', () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatTime(fiveMinutesAgo)).toBe('5m ago');
  });

  it('returns hours ago for timestamps within a day', () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
    expect(formatTime(threeHoursAgo)).toBe('3h ago');
  });

  it('returns days ago for timestamps within a week', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString();
    expect(formatTime(twoDaysAgo)).toBe('2d ago');
  });

  it('returns locale date for timestamps older than a week', () => {
    const twoWeeksAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000);
    const result = formatTime(twoWeeksAgo.toISOString());
    expect(result).toBe(twoWeeksAgo.toLocaleDateString());
  });
});

describe('formatSessionId', () => {
  it('returns first 8 characters of the ID', () => {
    expect(formatSessionId('abc123def456')).toBe('abc123de');
    expect(formatSessionId('12345678901234567890')).toBe('12345678');
  });

  it('returns full string if less than 8 characters', () => {
    expect(formatSessionId('abc')).toBe('abc');
  });
});

describe('getStatusDotClass', () => {
  it('returns correct class for RUNNING', () => {
    expect(getStatusDotClass('RUNNING')).toBe('bg-emerald-500');
  });

  it('returns correct class for AWAITING_INPUT with pulse', () => {
    expect(getStatusDotClass('AWAITING_INPUT')).toBe('bg-amber-400 animate-pulse');
  });

  it('returns correct class for INTERRUPTING', () => {
    expect(getStatusDotClass('INTERRUPTING')).toBe('bg-amber-500');
  });

  it('returns correct class for ERROR', () => {
    expect(getStatusDotClass('ERROR')).toBe('bg-rose-500');
  });

  it('returns correct class for CREATED', () => {
    expect(getStatusDotClass('CREATED')).toBe('bg-blue-400');
  });

  it('returns empty string for undefined', () => {
    expect(getStatusDotClass(undefined)).toBe('');
  });

  it('returns empty string for unknown state', () => {
    expect(getStatusDotClass('UNKNOWN')).toBe('');
  });
});
