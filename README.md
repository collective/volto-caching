# Volto caching tests

<div align="center">

[![Code Quality](https://github.com/collective/volto-caching/actions/workflows/main.yml/badge.svg)](https://github.com/collective/volto-caching/actions/workflows/main.yml)

[![GitHub contributors](https://img.shields.io/github/contributors/collective/volto-caching)](https://github.com/collective/volto-caching)
[![GitHub Repo stars](https://img.shields.io/github/stars/collective/volto-caching?style=social)](https://github.com/collective/volto-caching)

</div>


## What is this?

An integration test suite that validates the HTTP caching behaviour of a full
[Plone](https://plone.org) / [Volto](https://github.com/plone/volto) stack sitting
behind [Varnish](https://varnish-cache.org/). It spins up the whole stack with
Docker Compose and drives it with `pytest` + `httpx` to assert on cache headers,
cache hits/misses, manual `PURGE`/`BAN` invalidation, and automatic purging across
one or more Varnish instances.

The Compose stack wires together:

| Service | Image | Role |
| --- | --- | --- |
| `webserver` | `traefik:v3.7` | Edge router; splits public vs. internal (`X-Varnish-Routed`) traffic |
| `varnish` | `varnish:8.0.2` | Caching proxy (VCL in [`etc/varnish.vcl`](etc/varnish.vcl)) |
| `frontend` | Volto `19.1.4` | Plone React frontend (SSR) |
| `backend` | Plone `6.2.1` | `plone.restapi` backend with `plone.app.caching` |
| `purger` | `ghcr.io/kitconcept/cluster-purger` | Propagates purge requests to every Varnish instance |

Plone and Volto versions are pinned in the [`Makefile`](Makefile) (`PLONE_VERSION`,
`VOLTO_VERSION`) and can be overridden via the `PLONE_VERSION` / `VOLTO_VERSION`
environment variables consumed by [`docker-compose.yml`](docker-compose.yml).


## Requirements

- [Docker](https://docs.docker.com/get-docker/) with the Compose plugin
- [uv](https://docs.astral.sh/uv/) for Python dependency management


## Setup

Clone this repository, then install the Python environment and build the
container images:

```shell
make install
make containers-prepare
```


## Run tests

```shell
make test
```

You can pass extra arguments straight through to `pytest`, e.g. run a single
module:

```shell
make test tests/test_caching.py
```


## Other commands

Run `make help` to list every available target. The most useful ones:

### Start / stop the containers

```shell
make containers-start
make containers-stop
```

### Reload the Varnish configuration

After editing [`etc/varnish.vcl`](etc/varnish.vcl), reload it without restarting
the container:

```shell
make reload-varnish-config
```

### Lint and format

```shell
make lint      # check (and auto-fix) with ruff
make format    # sort imports and format with ruff
```

### Clean the environment

```shell
make clean
```
