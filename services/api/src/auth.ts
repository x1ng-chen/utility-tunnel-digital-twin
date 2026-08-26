import type { FastifyReply, FastifyRequest, preHandlerHookHandler } from 'fastify';

export type AuthUser = {
  id: string;
  roles: string[];
  permissions: string[];
};

declare module '@fastify/jwt' {
  interface FastifyJWT {
    user: AuthUser;
  }
}

export async function authenticate(request: FastifyRequest, reply: FastifyReply): Promise<void> {
  try {
    await request.jwtVerify();
  } catch {
    await reply.code(401).send({ error: 'unauthorized', message: 'Authentication is required.' });
    return;
  }
}

export function requirePermission(permission: string): preHandlerHookHandler {
  return async (request, reply) => {
    if (!request.user.permissions.includes(permission)) {
      await reply.code(403).send({ error: 'forbidden', message: 'Insufficient permission.' });
      return;
    }
  };
}
