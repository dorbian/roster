# Security notes

This is an MVP and should be treated as a small private community service, not a hardened enterprise identity system yet.

Implemented now:

- password hashing with PBKDF2-SHA256;
- server-side session storage;
- `HttpOnly` session cookies;
- `SameSite=Lax` cookies;
- private game visibility by membership;
- no public roster listing;
- invite-code-only joins;
- no GamePoint password collection.

Recommended before wider use:

- run only behind HTTPS;
- add CSRF tokens to forms;
- add login rate limiting;
- add password reset or magic-link login;
- add host score correction audit logs;
- add database backups;
- add reverse-proxy security headers;
- optionally move sessions to a signed cookie or Redis when scaling horizontally.
