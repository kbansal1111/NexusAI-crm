/**
 * Simple logger implementation to wrap console methods.
 *
 * info/debug/log are no-ops in production so end users get a clean console;
 * warn/error always pass through (they signal real problems worth reporting).
 */
const isDev = process.env.NODE_ENV !== "production";

export const logger = {
  info: (...args: any[]) => { if (isDev) console.info(...args); },
  warn: (...args: any[]) => console.warn(...args),
  error: (...args: any[]) => console.error(...args),
  debug: (...args: any[]) => { if (isDev) console.debug(...args); },
  log: (...args: any[]) => { if (isDev) console.log(...args); },
};
