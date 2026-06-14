# emulator/

Throwaway run-kit that drives **real DJI Pilot 2 (in BlueStacks)** against the
**real fieldhub** — cert-free, plain HTTP, no postgres. Separate from the
production `field` compose profile.

Full procedure: [`docs/emulator-validation.md`](../docs/emulator-validation.md).

```bash
cp .env.emulator.example .env.emulator        # fill in DJI app creds
docker compose --env-file .env.emulator -f docker-compose.emulator.yml up -d --build
```

`--env-file` is required: compose interpolates `${VAR}` in the compose file from
it. (`environment:` overrides `env_file:`, so a plain `env_file` would be
silently ignored for these vars.)

- `docker-compose.emulator.yml` — fieldhub (plain HTTP) + MinIO + nginx.
- `nginx.conf` — the single device-facing port (8080); bucket paths → MinIO
  preserving the signed Host, everything else → fieldhub.
- `seed-wayline.sh` — register a KMZ into the wayline library (stands in for the
  monorepo backend's dispatch).
- `.env.emulator.example` — copy to `.env.emulator` (git-ignored) and fill in.
