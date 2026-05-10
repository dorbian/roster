# Design: roster.thebigtree.life

## Goal

Build a private roster website for hosted card-game evenings that feel familiar next to GamePoint: friendly, colorful, game-card based, simple join flow, and not tournament-admin heavy.

The site is an unofficial companion system. It does not automate GamePoint rooms, scrape GamePoint, collect GamePoint passwords, or expose public rosters.

## Visual direction

The UI borrows the broad feeling of a casual social game portal:

- dark purple background;
- warm yellow/orange call-to-action buttons;
- rounded cream-colored cards;
- simple game cards;
- friendly casino/card-game accents;
- mobile-friendly layout.

It should not copy GamePoint branding, logos, assets, names, or protected artwork.

## Authentication

MVP authentication is local:

- username;
- display name;
- GamePoint player name;
- password;
- server-side session token stored in SQLite;
- browser session held using an `HttpOnly`, `SameSite=Lax` cookie.

Facebook Login is intentionally deferred. It adds platform setup and review risk while not proving ownership of a GamePoint account.

## Privacy model

There are no public rosters.

A user can see a game only when:

- they created it;
- they joined it through the private invite URL;
- they are already a member.

The dashboard shows only the logged-in user's active memberships.

## Game lifecycle

```text
setup -> active -> complete
```

### setup

The host creates a game and receives a private invite URL.
Players join while the game is in setup.

### active

The host locks the roster and starts the game.
The server creates round 1.
Players submit scores for their table.

### complete

After the final configured round, the game is completed and final standings are shown.

## Round progression rule

The frontend never decides progression.

The server checks whether all tables in the current round have status `submitted`.
When true:

1. the current round is marked complete;
2. if this was the final round, the game is marked complete;
3. otherwise the next round is generated immediately.

## Assignment model

The round engine creates:

- tables;
- table players;
- byes when needed.

Every active player receives one round assignment:

- table seat; or
- bye.

Byes are balanced by preferring players with the fewest previous byes.

## Future improvements

- stronger anti-repeat pairing;
- host score correction/audit log;
- password reset or magic-link login;
- configurable bye points;
- game-specific scoring rules;
- room-name field for GamePoint room coordination;
- export CSV standings;
- WebSocket/SSE live updates;
- OIDC provider support if needed.
