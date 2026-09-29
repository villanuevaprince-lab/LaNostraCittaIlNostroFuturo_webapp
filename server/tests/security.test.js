import session from 'express-session';
import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';

describe('protezione richieste', () => {
  it('fornisce un token CSRF e imposta una sessione HttpOnly', async () => {
    const app = createApp({ sessionStore: new session.MemoryStore() });
    const response = await request(app).get('/api/auth/csrf');
    expect(response.status).toBe(200);
    expect(response.body.csrfToken).toMatch(/^[a-f0-9]{64}$/);
    expect(response.headers['set-cookie'][0]).toContain('HttpOnly');
  });

  it('rifiuta richieste di modifica prive di token CSRF', async () => {
    const app = createApp({ sessionStore: new session.MemoryStore() });
    const response = await request(app).post('/api/auth/login').send({
      email: 'mario@example.com',
      password: 'Password123'
    });
    expect(response.status).toBe(403);
    expect(response.body.error.code).toBe('CSRF_MISSING');
  });

  it('non espone l’header Express', async () => {
    const app = createApp({ sessionStore: new session.MemoryStore() });
    const response = await request(app).get('/api/auth/csrf');
    expect(response.headers['x-powered-by']).toBeUndefined();
  });
});
