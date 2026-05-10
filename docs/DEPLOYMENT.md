# Deployment notes

## Container build

The project builds to an OCI-compatible image and does not require Python dependencies outside the standard library.

```bash
podman build -t ghcr.io/thebigtree/roster.thebigtree.life:latest .
```

The application listens on port `8500` inside the container.

## Runtime behind Traefik

For production, TLS should terminate at Traefik and Traefik should route to the container over plain HTTP on port `8500`.

```text
https://roster.thebigtree.life -> http://roster-thebigtree-life:8500
```

Example local container start without publishing the app directly to the internet:

```bash
podman volume create roster-data
podman run -d \
  --name roster-thebigtree-life \
  --restart unless-stopped \
  --expose 8500 \
  -e PORT=8500 \
  -e ROSTER_HOSTNAME=roster.thebigtree.life \
  -v roster-data:/data:Z \
  ghcr.io/thebigtree/roster.thebigtree.life:latest
```

For a quick local test without Traefik, temporarily publish the port:

```bash
podman run --rm -p 8500:8500 \
  -e PORT=8500 \
  -e ROSTER_HOSTNAME=roster.thebigtree.life \
  -v roster-data:/data:Z \
  ghcr.io/thebigtree/roster.thebigtree.life:latest
```

Then open `http://127.0.0.1:8500`.

## Podman compose

`compose.podman.yaml` exposes the internal container port and includes Traefik labels:

```bash
podman compose -f compose.podman.yaml up -d
```

The Traefik labels expect a Traefik setup that can discover Podman/Docker labels and reach the container network. If your Traefik uses a fixed external network, attach the service to that network in `compose.podman.yaml`.

## Quadlet

The `deploy/` directory contains a Podman Quadlet unit and volume file:

```text
deploy/roster.container
deploy/roster-data.volume
```

The Quadlet unit does not publish the app port directly. It relies on Traefik discovery/routing and the service label:

```text
traefik.http.services.roster.loadbalancer.server.port=8500
```

## Environment variables

| Name | Default | Description |
|---|---|---|
| `PORT` | `8500` | HTTP port inside the container |
| `BIND` | `0.0.0.0` | HTTP bind address |
| `ROSTER_HOSTNAME` | `roster.thebigtree.life` | Hostname used when showing invite URLs |
| `ROSTER_DATA_DIR` | `/data` | Persistent database directory |
| `SESSION_TTL_SECONDS` | `1209600` | Session lifetime, default 14 days |

## GitHub Actions

`.github/workflows/container.yml` builds and publishes a multi-arch OCI image for:

- `linux/amd64`
- `linux/arm64`
- `linux/ppc64le`

On push to `main`, the workflow publishes `latest` to GHCR.
On tags starting with `v`, it publishes the tag as well.
Pull requests build the image but do not push it.
