import 'dotenv/config';
import { z } from 'zod';

const environment = z.object({
  DATABASE_URL: z.string().url(),
  JWT_SECRET: z.string().min(32),
  PORT: z.coerce.number().int().min(1).max(65535).default(8080),
  HOST: z.string().default('127.0.0.1'),
  WEB_ORIGIN: z.string().url(),
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
});

const parsed = environment.safeParse(process.env);

if (!parsed.success) {
  throw new Error(`Invalid environment configuration: ${parsed.error.issues.map((issue) => issue.path.join('.')).join(', ')}`);
}

export const config = parsed.data;
