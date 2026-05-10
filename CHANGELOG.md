# Changelog

## v0.7

- Updated the default runtime image to `ghcr.io/dorbian/roster:latest`.
- Updated systemd environment, Podman compose, Quadlet container example, README, deployment docs, and GHCR workflow metadata to use the Dorbian image path.
- Kept Traefik externally managed; installer still does not edit or reload Traefik configuration.

## v0.6

- Clarified that Traefik is managed outside this package.
- Updated the installer output so it does not instruct automatic or required Traefik edits.
- Kept `deploy/traefik/roster-snippet.yml` only as a manual reference snippet.
- Confirmed roster-owned files remain under `/opt/groster`.
- Confirmed the systemd service still exposes the container as `game-roster` on the shared Podman network for Traefik DNS routing.

## v0.5

- Added `/opt/groster` deployment layout.
- Added systemd-managed Podman service.
- Added local persistent data mount for SQLite/runtime data.
- Added Traefik reference routing to `http://game-roster:8500`.
