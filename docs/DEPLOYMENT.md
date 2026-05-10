# Deployment notes

## Target host

The intended single-host deployment target is:

```text
192.168.0.203
```

Traefik is already running on that host with a file-provider config under:

```text
/opt/honsefarm/traefik/dynamic/routers.yml
```

The roster installer and systemd service **do not edit Traefik configuration**. Traefik is managed separately. The files under `deploy/traefik/` are reference snippets only, for manual review.

The roster application should not use Traefik container labels on this host. Traefik should route through the shared Podman network to the container DNS name:

```text
http://game-roster:8500
```

## Local host layout

All roster-specific source, configuration, and persistent data should live under:

```text
/opt/groster
```

Recommended layout:

```text
/opt/groster/
  source/   checked-out or copied application source
  data/     SQLite database and runtime data
  config/   environment file used by systemd
```

The container stores data in `/data`; the host bind mount is:

```text
/opt/groster/data:/data:Z
```

SQLite database path inside the container:

```text
/data/roster.db
```

## Install from the full source zip

Copy the zip to `192.168.0.203`, unpack it, and run the installer from the repository root:

```bash
unzip gamepoint-roster-v0.7-dorbian-roster-image.zip
cd gamepoint-roster
sudo ./scripts/install-systemd-service.sh
```

The installer copies the complete source tree to:

```text
/opt/groster/source
```

It installs the environment file only if it does not already exist:

```text
/opt/groster/config/game-roster.env
```

This prevents local production edits from being overwritten on later source updates.

The installer performs only roster-owned changes:

- creates `/opt/groster` directories
- copies the source tree to `/opt/groster/source`
- installs `/opt/groster/config/game-roster.env` only when missing
- installs `/etc/systemd/system/game-roster.service`
- enables the `game-roster.service`

It does **not** modify `/opt/honsefarm/traefik/dynamic/routers.yml` or any other Traefik file.

## Install or update source from Git

If this repository is hosted in Git, source can also be placed under `/opt/groster/source` with:

```bash
sudo ./scripts/update-source.sh https://github.com/dorbian/roster.git main
```

Adjust the repository URL and branch as needed.

## systemd service

The systemd unit is:

```text
deploy/systemd/game-roster.service
```

It is installed as:

```text
/etc/systemd/system/game-roster.service
```

Default runtime config:

```text
deploy/systemd/game-roster.env
```

Installed runtime config:

```text
/opt/groster/config/game-roster.env
```

Start or restart:

```bash
sudo systemctl restart game-roster.service
sudo systemctl status game-roster.service --no-pager
sudo journalctl -u game-roster.service -f
```

The service runs the container as:

```text
game-roster
```

and attaches it to the Podman network:

```text
honsefarm
```

This is the name Traefik should use for routing.

## Traefik file-provider config

Traefik is intentionally manual for this deployment. The current installer will not patch, overwrite, reload, or restart Traefik.

If Traefik still needs a roster entry, merge this router manually into `/opt/honsefarm/traefik/dynamic/routers.yml` under `http.routers`:

```yaml
    roster:
      rule: "Host(`roster.thebigtree.life`)"
      entryPoints: ["websecure"]
      service: roster-svc
      tls:
        certResolver: letsencrypt
```

Merge this service manually under `http.services`:

```yaml
    roster-svc:
      loadBalancer:
        servers:
          - url: "http://game-roster:8500"
```

A standalone reference snippet is included at:

```text
deploy/traefik/roster-snippet.yml
```

Because you already added the Traefik config, normally no Traefik action is required from this package.

## Container build

The project builds to an OCI-compatible image and does not require Python dependencies outside the standard library.

```bash
podman build -t ghcr.io/dorbian/roster:latest .
```

The application listens on port `8500` inside the container.

## Runtime environment variables

| Name | Default | Description |
|---|---|---|
| `PORT` | `8500` | HTTP port inside the container |
| `BIND` | `0.0.0.0` | HTTP bind address |
| `ROSTER_HOSTNAME` | `roster.thebigtree.life` | Hostname used when showing invite URLs |
| `ROSTER_DATA_DIR` | `/data` | Persistent database directory |
| `SESSION_TTL_SECONDS` | `1209600` | Session lifetime, default 14 days |

The systemd-specific env file also contains:

| Name | Default | Description |
|---|---|---|
| `ROSTER_IMAGE` | `ghcr.io/dorbian/roster:latest` | Image pulled by systemd before starting |
| `ROSTER_CONTAINER_NAME` | `game-roster` | Stable Podman DNS/container name used by Traefik |
| `PODMAN_NETWORK` | `honsefarm` | Shared network Traefik must also be attached to |
| `GROSTER_ROOT` | `/opt/groster` | Root directory for this deployment |
| `GROSTER_SOURCE_DIR` | `/opt/groster/source` | Source checkout/copy target |
| `GROSTER_DATA_DIR` | `/opt/groster/data` | Host persistent data directory |
| `GROSTER_CONFIG_DIR` | `/opt/groster/config` | Host config directory |

## Podman compose

`compose.podman.yaml` is kept for local tests and uses the same production assumptions:

- container name: `game-roster`
- network: external `honsefarm`
- data bind mount: `/opt/groster/data:/data:Z`
- no Traefik labels

```bash
podman compose -f compose.podman.yaml up -d
```

## Quadlet

A Quadlet container file remains available at:

```text
deploy/roster.container
```

The preferred production deployment for `192.168.0.203` is now the explicit systemd service in `deploy/systemd/`, because it also manages the `/opt/groster` layout and image pulls.

## GitHub Actions

The repository includes a multi-arch container build workflow at:

```text
.github/workflows/container.yml
```

It is intended to publish an OCI image for use by the systemd service.
