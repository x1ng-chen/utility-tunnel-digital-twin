import { randomUUID } from 'node:crypto';
import Fastify from 'fastify';
import cors from '@fastify/cors';
import jwt from '@fastify/jwt';
import { config } from './config.js';
import { db } from './db.js';
import { registerAuthRoutes } from './routes/auth.js';
import { registerOperationsRoutes } from './routes/operations.js';

const app = Fastify({
  logger: true,
  genReqId: () => randomUUID(),
  bodyLimit: 1_048_576,
});

await app.register(cors, {
  origin: config.WEB_ORIGIN,
  methods: ['GET', 'POST', 'PUT', 'PATCH'],
  allowedHeaders: ['authorization', 'content-type', 'x-request-id'],
  maxAge: 600,
});

await app.register(jwt, { secret: config.JWT_SECRET });

app.addHook('onSend', async (_request, reply) => {
  reply.header('X-Content-Type-Options', 'nosniff');
  reply.header('X-Frame-Options', 'DENY');
  reply.header('Referrer-Policy', 'no-referrer');
  reply.header('Cache-Control', 'no-store');
});

app.setErrorHandler((error, request, reply) => {
  request.log.error(error);
  if (reply.sent) return;
  reply.code(500).send({ error: 'internal_error', message: 'An unexpected error occurred.', requestId: request.id });
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
