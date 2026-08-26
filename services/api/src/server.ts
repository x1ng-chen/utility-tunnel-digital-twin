import { randomUUID } from 'node:crypto';
import Fastify from 'fastify';
import cors from '@fastify/cors';
import jwt from '@fastify/jwt';
import { config } from './config.js';
import { db } from './db.js';
import { FixedWindowRateLimiter } from './rate-limit.js';
import { registerAuthRoutes } from './routes/auth.js';
import { registerOperationsRoutes } from './routes/operations.js';

const app = Fastify({
  logger: {
    level: config.LOG_LEVEL,
    redact: ['req.headers.authorization', 'req.headers.cookie', 'req.body.password', 'req.body.passwordHash'],
  },
  genReqId: () => randomUUID(),
  bodyLimit: 1_048_576,
});
const apiLimiter = new FixedWindowRateLimiter(240, 60_000);
const loginLimiter = new FixedWindowRateLimiter(10, 60_000);

await app.register(cors, {
  origin: config.WEB_ORIGIN,
  methods: ['GET', 'POST', 'PUT', 'PATCH'],
  allowedHeaders: ['authorization', 'content-type', 'x-request-id'],
  maxAge: 600,
});

await app.register(jwt, { secret: config.JWT_SECRET });

app.addHook('onRequest', async (request, reply) => {
  const path = request.url.split('?')[0] ?? request.url;
  if (path === '/v1/health' || path === '/v1/ready') return;
  const limiter = path === '/v1/auth/login' ? loginLimiter : apiLimiter;
  const decision = limiter.check(`${path === '/v1/auth/login' ? 'login' : 'api'}:${request.ip}`);
  reply.header('X-RateLimit-Limit', path === '/v1/auth/login' ? '10' : '240');
  reply.header('X-RateLimit-Remaining', String(decision.remaining));
  if (!decision.allowed) {
    reply.header('Retry-After', String(decision.retryAfterSeconds));
    return reply.code(429).send({ error: 'rate_limited', message: 'Too many requests. Please retry later.', requestId: request.id });
  }
});

app.addHook('onSend', async (request, reply) => {
  reply.header('X-Content-Type-Options', 'nosniff');
  reply.header('X-Frame-Options', 'DENY');
  reply.header('Referrer-Policy', 'no-referrer');
  reply.header('Permissions-Policy', 'geolocation=(), microphone=(), camera=()');
  reply.header('Cross-Origin-Opener-Policy', 'same-origin');
  reply.header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'");
  reply.header('X-Request-Id', request.id);
  if (config.NODE_ENV === 'production') reply.header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
  reply.header('Cache-Control', 'no-store');
});

app.setErrorHandler((error, request, reply) => {
  request.log.error(error);
  if (reply.sent) return;
  reply.code(500).send({ error: 'internal_error', message: 'An unexpected error occurred.', requestId: request.id });
});

app.setNotFoundHandler((request, reply) => {
  reply.code(404).send({ error: 'not_found', message: 'Route not found.', requestId: request.id });
});

await registerAuthRoutes(app);
await registerOperationsRoutes(app);

const shutdown = async (signal: string) => {
  app.log.info({ signal }, 'shutting down');
  await app.close();
  await db.end();
  process.exit(0);
};

process.once('SIGINT', () => void shutdown('SIGINT'));
process.once('SIGTERM', () => void shutdown('SIGTERM'));

try {
  await app.listen({ port: config.PORT, host: config.HOST });
} catch (error) {
  app.log.error(error);
  await db.end();
  process.exit(1);
}
