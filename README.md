# Coders Fast Start

Build a standard, commit-pinned HTTP image that also supports Coders warm runtime environments.
Application code stays a normal HTTP server. Existing `coders.json` endpoint, permission and budget declarations apply.

Create `.github/workflows/coders-build.yml` in a public repository:

```yaml
name: Build Coders image
on:
  push:
    branches: [main]
  workflow_dispatch:
permissions:
  contents: read
  packages: write
  id-token: write
  attestations: write
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cykim8811/coders-fast-start@main # Pin a full action commit for deployment.
        with:
          runtime: nodejs-22
          start: npm start
```

For Python:

```yaml
with:
  runtime: python-3.12
  start: python -m uvicorn main:app --host 0.0.0.0 --port 8080
```

The GHCR package must be Public. The output tag is `sha-<full application commit>` and includes GitHub Actions provenance.
Use an immutable action commit rather than `main` in production workflows.

## Runtime contract

- Linux/amd64, pinned Debian Bookworm Python 3.12 or Node.js 22 runtime.
- `/app` contains application code and all runtime dependencies and is read-only at execution time.
- The start command runs in `/app`, with `PORT=8080` and `HOME=/tmp`.
- Normal resource-scoped `DATABASE_URL`, optional `REDIS_URL`, and `CODERS_URL` are supplied by Core.
- `/tmp` is temporary. Persistent data belongs in the workspace services.
- Package installation and compilation run during the build. The runtime uses the official base OS without extra system packages.
- Payload: at most 512 MiB of regular-file content by default and 50,000 archive entries. Device files and escaping links are rejected.

Python uses `uv.lock`, `requirements.txt`, or `pyproject.toml` in that order and installs dependencies into `/app/.python`.
Node defaults to `npm ci`, `npm run build --if-present`, and `npm prune --omit=dev`.
Commit the lock file. `PYTHONPATH` and executable search paths are supplied automatically.

Override the build command for pnpm, yarn, a monorepo or another project build:

```yaml
with:
  runtime: nodejs-22
  start: node dist/server.js
  build: corepack enable && pnpm install --frozen-lockfile && pnpm run build && pnpm prune --prod
```

An optional `context` selects the application directory. `image` overrides the default `ghcr.io/<caller-repository>` package.
`.git`, `.env`, `.env.*`, `.venv`, local `node_modules` and Python caches are excluded from the build context.

## Warm execution

Core prepares bounded pools of empty environments. After verification, an environment is exclusively assigned to one resource,
its code is attached, its existing resource budget and service connections are enabled, and the start command runs.
Used environments are destroyed; they are never reassigned to another resource. An empty pool creates the same environment on demand.
App imports, migrations and DB/Redis startup still contribute to startup latency. General OCI-image deployment remains available.

Build outputs are also ordinary runnable images. The fast-start descriptor is in the `kr.coders.fast-start` image label.
The runtime release, command and payload are bound to the verified application image digest.

The build action contains no Coders Core server source or credentials.
