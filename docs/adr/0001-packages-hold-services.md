# 1. packages/ holds services as well as libraries

**Status:** accepted

## Context

The first cut of the restructure used three top-level directories: `packages/`
for shared libraries, `services/` for long-running processes, and `apps/` for
user-facing surfaces. The reference monorepo this repo is modelled on does not
work that way — its `packages/api` and `packages/odoo-sync` are both long-running
services sitting alongside `packages/config` and `packages/db`, and `apps/` holds
only the two Next.js frontends.

## Decision

Follow the reference. `packages/` holds both libraries and services; `apps/` is
reserved for user-facing surfaces.

## Consequences

`packages/openalgo` and `packages/tradingview-mcp` sit next to `packages/config`
and `packages/domain`. The distinction between "library" and "service" is carried
by whether the package has an entry point, not by its parent directory — which is
already how a reader tells them apart in practice.

The `services/` commits were rewritten before pushing, so history goes straight to
the final layout rather than moving 1,600 vendored files twice.
