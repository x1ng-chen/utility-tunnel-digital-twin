import type { FastifyInstance } from 'fastify';
import { z } from 'zod';
import { writeAudit } from '../audit.js';
import { inTransaction } from '../db.js';
import { verifyPassword } from '../password.js';

const loginBody = z.object({
  email: z.string().trim().email().max(320).transform((value) => value.toLowerCase()),
  password: z.string().min(1).max(256),
});

type LoginAccount = {
  id: string;
  email: string;
  display_name: string;
  password_hash: string;
  roles: string[];
  permissions: string[];
};

export async function registerAuthRoutes(app: FastifyInstance): Promise<void> {
  app.post('/v1/auth/login', async (request, reply) => {
    const body = loginBody.safeParse(request.body);
    if (!body.success) return reply.code(400).send({ error: 'invalid_request', message: 'Invalid email or password format.' });

    const accountResult = await inTransaction(async (client) => {
      const result = await client.query<LoginAccount>(
        `SELECT u.id, u.email, u.display_name, u.password_hash,
                COALESCE(array_agg(DISTINCT r.code) FILTER (WHERE r.code IS NOT NULL), '{}') AS roles,
                COALESCE(array_agg(DISTINCT p.code) FILTER (WHERE p.code IS NOT NULL), '{}') AS permissions
         FROM app_user u
         LEFT JOIN user_role ur ON ur.user_id = u.id
         LEFT JOIN app_role r ON r.id = ur.role_id
         LEFT JOIN role_permission rp ON rp.role_id = r.id
         LEFT JOIN permission p ON p.id = rp.permission_id
         WHERE u.email = $1 AND u.is_active = true
         GROUP BY u.id`,
        [body.data.email],
      );
      // An email is an account identifier. Refuse ambiguous data instead of
      // authenticating whichever duplicate row PostgreSQL happens to return.
      return result.rowCount === 1 ? result.rows[0] : null;
    });

    if (!accountResult || !(await verifyPassword(body.data.password, accountResult.password_hash))) {
      return reply.code(401).send({ error: 'invalid_credentials', message: 'Invalid email or password.' });
    }

    await inTransaction(async (client) => {
      await client.query('UPDATE app_user SET last_login_at = now() WHERE id = $1', [accountResult.id]);
      await writeAudit(client, {
        actorId: accountResult.id,
        action: 'auth.login',
        resourceType: 'app_user',
        resourceId: accountResult.id,
        requestId: request.id,
        detail: { email: accountResult.email },
      });
    });

    const token = await reply.jwtSign({ id: accountResult.id, roles: accountResult.roles, permissions: accountResult.permissions }, { expiresIn: '15m' });
    return reply.send({
      accessToken: token,
      tokenType: 'Bearer',
      expiresInSeconds: 900,
      user: { id: accountResult.id, email: accountResult.email, displayName: accountResult.display_name, roles: accountResult.roles },
    });
  });
}
