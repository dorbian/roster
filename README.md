# roster.thebigtree.life

Private invite-only roster and round engine for GamePoint-style card-game evenings.

This MVP intentionally does not use GamePoint authentication. Users create local accounts, enter their GamePoint player name, and then create or join private games by invite URL. There is no public roster directory.

## Features

- Local username/password registration.
- Session-cookie authentication using `HttpOnly` and `SameSite=Lax` cookies.
- Logged-in dashboard showing only games the user belongs to.
- Private invite URL per game: `https://roster.thebigtree.life/j/<CODE>`.
- Hosts can create games, lock rosters, and start rounds.
- Automatic table assignment based on signed-up player count.
- Bye balancing for uneven rosters.
- Score entry per table.
- Server-side automatic progression when all tables in the current round are submitted.
- OCI-compatible container for Podman, Docker, Kubernetes, Quadlet, or a direct systemd-managed Podman service.
- GitHub Actions workflow for multi-arch GHCR image builds: amd64, arm64, and ppc64le.
- Container listens on port `8500`; HTTPS is expected to terminate at Traefik.

## Local run

```bash
python3 app/server.py
```

Open `http://127.0.0.1:8500`.

## Podman build

```bash
podman build -t roster.thebigtree.life:dev .
podman run --rm -p 8500:8500 \
  -e PORT=8500 \
  -e ROSTER_HOSTNAME=roster.thebigtree.life \
  -v roster-data:/data:Z \
  roster.thebigtree.life:dev
```

## Podman compose

```bash
podman compose -f compose.podman.yaml up -d
```

## Expected published image

```text
ghcr.io/dorbian/roster:latest
```

Change the image name in `.github/workflows/container.yml` if the repository is hosted under another owner/name.

## Persistent data

SQLite database path:

```text
/data/roster.db
```

For the target host deployment, mount `/opt/groster/data` to `/data` in the container. The downloaded or copied source tree should live under `/opt/groster/source`, and runtime configuration under `/opt/groster/config`.


## Target deployment on 192.168.0.203

The production-style single-host deployment uses `/opt/groster` as the only roster-owned host root:

```text
/opt/groster/source   application source
/opt/groster/data     SQLite database and runtime data
/opt/groster/config   systemd environment file
```

Install from an unpacked source zip:

```bash
sudo ./scripts/install-systemd-service.sh
```

The systemd service runs a Podman container named `game-roster` on the `honsefarm` Podman network. Traefik should route to the Podman DNS name, not the host IP:

```yaml
url: "http://game-roster:8500"
```

The installer does not modify Traefik. Your existing `/opt/honsefarm/traefik/dynamic/routers.yml` remains untouched. See `docs/DEPLOYMENT.md`; `deploy/traefik/roster-snippet.yml` is only a manual reference.
