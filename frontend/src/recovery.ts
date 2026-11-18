import { Code, ConnectError } from "@connectrpc/connect";

export const STREAM_IDLE_TIMEOUT_MS = 6000;
export const STREAM_CHECK_INTERVAL_MS = 250;

export function retryable(error: unknown): boolean {
  if (error instanceof ConnectError) {
    return error.code === Code.Unavailable || error.code === Code.DeadlineExceeded ||
      (error.code === Code.Unknown && (error.cause instanceof TypeError || error.rawMessage === "missing trailer"));
  }
  return error instanceof TypeError;
}

export function backoff(attempt: number): number {
  return Math.min(250 * 2 ** Math.min(attempt, 3), 2000);
}

export function pause(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) { reject(signal.reason); return; }
    function abort() {
      clearTimeout(timer);
      reject(signal.reason);
    }
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}

export async function retryRead<T>(
  call: (timeoutMs: number) => Promise<T>, signal?: AbortSignal,
): Promise<T> {
  const deadline = performance.now() + 5000;
  const cancellation = signal ?? new AbortController().signal;
  for (let attempt = 0; ; attempt++) {
    cancellation.throwIfAborted();
    const remaining = deadline - performance.now();
    if (remaining <= 0) throw new ConnectError("Read deadline expired", Code.DeadlineExceeded);
    try {
      return await call(remaining);
    } catch (error) {
      if (cancellation.aborted || !retryable(error) || attempt === 2) throw error;
      const delay = backoff(attempt);
      if (performance.now() + delay >= deadline) throw error;
      await pause(delay, cancellation);
    }
  }
}
