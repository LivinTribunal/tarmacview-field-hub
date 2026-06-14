# 2026-06-14 — TarmacView ⇄ Field Hub integration topology

## Context

The field hub is a LAN-only, offline-capable gateway on the field laptop.
TarmacView itself deploys two ways: **cloud** (AWS Lambda backend + hosted
frontend) and **local Docker** (the full stack on the laptop). Today's baseline:
the backend reaches the hub over REST with an `X-Hub-Secret` shared secret on the
compose network; the frontend only ever calls the backend; a cloud (Lambda)
deployment has no hub and degrades to "no hub"; field setup is manual (hand-edited
`.env.docker`, certs).

We need to decide how TarmacView connects to the hub regardless of where
TarmacView runs, and how cloud-planned missions reach an offline field stack.

The constraint that shapes everything: airports are often **offline**, and a
cloud backend can **never** reach a NAT'd, offline field laptop — there is no
inbound path. The operator's **browser/laptop is the only shared reachability
point** between a hosted TarmacView and a local hub.

## Decision

Three scenarios; two supported now, one deferred:

1. **Offline field** (no internet) — the whole stack runs locally in Docker; the
   backend reaches the hub over the compose network. **Primary path.**
2. **Connected field** (internet present) — the hosted web app runs in the
   browser, which talks to the **local hub directly over the LAN**
   (browser-bridge). **Phase 3.**
3. **Office planning** — cloud app, no hub present; graceful "no hub".

**Connection model:** local-Docker co-located first; browser-bridge later. **No
cloud↔LAN tunnel** — it would require internet at the field (defeating offline)
and only helps the connected case the browser-bridge already covers.

**Mission availability:** support **both-local** (plan and fly in the local
stack) and **both-online** (cloud app + a reachable hub). The mixed case —
**cloud app while only the hub is offline** — requires **pre-trip pull sync** (the
local stack pulls the selected missions while still online, before going to the
field). That sync is **deferred**: not built until office-planning-then-offline-
flying is a real workflow. For offline work now, plan in the local stack.

**Packaging:** stay **Docker** — the hub needs EMQX (broker) and MinIO (object
store). No native app; a thin desktop/launcher wrapper only if operators struggle
with a script.

**Field launcher placement:** the one-command launcher lives in the **monorepo**
(it brings up the whole stack — backend, frontend, hub, EMQX, MinIO), reusing
this repo's `gen-certs.sh`.

**Connected-field media path:** the hub dials **out** to the cloud backend's
`POST /api/v1/field-link/media-events` (outbound through NAT works), so media
events still land when the backend is in the cloud.

**Scope:** single workspace / single pilot account, one field laptop per session.

## Alternatives rejected

- **Cloud↔LAN tunnel/relay** (the hub dials out to a cloud relay so the cloud
  backend can reach it): needs internet at the field and extra infra; only helps
  the connected case, already covered by the browser-bridge.
- **Frontend always direct to the hub** (drop the backend proxy): simpler for the
  web case but breaks the clean offline co-located path; keep the proxy for
  co-located, add the bridge only for the connected web case.
- **Native desktop app embedding the broker + object store**: large
  cross-platform cost, no gain over Docker.
- **Full live cloud↔field sync now**: premature; pre-trip pull is deferred until
  the workflow demands it.

## Consequences

- **Phase 1** (one-command offline setup) is the near-term focus and is what
  hardware day needs; it also removes today's manual `.env`/cert wiring.
- **Phase 3** (browser-bridge) introduces CORS + a hub-issued short-lived browser
  token + frontend hub discovery — a new browser-reachable hub surface that needs
  a security review.
- The **deferred pre-trip sync** is a known gap: cloud-planned missions are not
  available offline until it lands; offline work plans in the local stack.
- Supersedes the deployment notes in
  `2026-06-09-field-hub-local-cloud-api.md` (which assumed co-location only).
