export type RateLimitDecision = {
  allowed: boolean;
  remaining: number;
  retryAfterSeconds: number;
};

type Bucket = {
  startedAt: number;
  count: number;
};

export class FixedWindowRateLimiter {
  private readonly buckets = new Map<string, Bucket>();

  constructor(private readonly limit: number, private readonly windowMs: number, private readonly maximumBuckets = 10_000) {}

  check(key: string, now = Date.now()): RateLimitDecision {
    const current = this.buckets.get(key);
    if (!current && this.buckets.size >= this.maximumBuckets) {
      this.cleanup(now);
      if (this.buckets.size >= this.maximumBuckets) {
        return { allowed: false, remaining: 0, retryAfterSeconds: Math.max(1, Math.ceil(this.windowMs / 1_000)) };
      }
    }
    const bucket = !current || now - current.startedAt >= this.windowMs ? { startedAt: now, count: 0 } : current;
    bucket.count += 1;
    this.buckets.set(key, bucket);
    const retryAfterSeconds = Math.max(1, Math.ceil((bucket.startedAt + this.windowMs - now) / 1_000));
    return {
      allowed: bucket.count <= this.limit,
      remaining: Math.max(0, this.limit - bucket.count),
      retryAfterSeconds,
    };
  }

  private cleanup(now: number): void {
    for (const [key, bucket] of this.buckets) {
      if (now - bucket.startedAt >= this.windowMs) this.buckets.delete(key);
    }
  }
}
