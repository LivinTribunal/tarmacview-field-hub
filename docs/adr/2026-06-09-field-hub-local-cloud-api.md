# 2026-06-09 — Field Hub: local DJI Cloud API gateway for mission dispatch and media return

> The deployment/topology notes below (co-location only, browser straight to the
> backend) are partially superseded by
> `2026-06-14-tarmacview-fieldhub-integration-topology.md` — browser-bridge for
> the connected case, deferred pre-trip sync, and no cloud↔LAN tunnel. The core
> decision here — a local Cloud API gateway running alongside Pilot 2 — still
> stands.

## Context

Today the mission KMZ reaches the DJI controller by hand (file copy + manual
import into DJI Pilot 2), and recorded inspection media comes back by pulling
the aircraft's SD card. We want both directions automated, with hard
constraints set by airport field conditions:

- fully wireless — no USB cable, no SD card handling;
- offline-capable — airports often have no internet, so everything must run
  on a local network (travel router / laptop hotspot); only one-time office
  provisioning may touch the WAN;
- DJI Pilot 2 remains the flight app — no custom flight application to build
  and maintain;
- full-quality media — the originals from the aircraft storage, not the
  OcuSync live-view cache;
- integrates with the dockerized TarmacView stack already running on the
  field laptop.

The physical constraint that shapes everything: recorded media lives on the
aircraft's onboard storage, and the only software able to pull it off
wirelessly is DJI's own stack (Pilot 2 or a DJI Mobile SDK app). No
third-party peer-to-peer agent can reach it.

Fleet: Matrice 300 RTK / 350 RTK (RC Plus), Matrice 4T (RC Plus 2), Mavic 3
Enterprise — all supported by the Cloud API "Pilot feature set" with no Dock.

## Decision

Implement the device-facing surface of the DJI Cloud API (Pilot feature set)
as a new local service — the **Field Hub** — running in the existing docker
compose stack on the field laptop, under a `field` profile:

- `fieldhub` (FastAPI): device binding, wayline library, storage-credential
  issuing, media upload callbacks; bridges to the TarmacView backend over
  internal REST;
- EMQX as the MQTTS broker (device status, telemetry, events);
- MinIO as the S3-compatible store Pilot uploads media into directly;
- local CA / self-signed TLS, CA installed on each RC once.

DJI Pilot 2 on the RC connects to this "cloud" over the local WiFi. Mission
dispatch pushes the existing export KMZ into Pilot's route library; media
returns via Pilot's media-upload module (photos and video, originals).
Browser traffic keeps going only to `backend`, which proxies hub state.

Architecture spec with flows, integration surface, phasing and validation
checklist: `docs/specs/FIELD-HUB.md`.

## Alternatives rejected

- **Custom MSDK v5 flight app on the RC** — most automated option
  (programmatic mission start + MediaManager pull), but it replaces Pilot 2
  as the flight app, which violates the "no custom flight app" constraint and
  carries the highest maintenance burden.
- **LocalSend-style peer transfer agent (PC app + RC app)** — works for
  pushing the KMZ file, but physically cannot retrieve media from the
  aircraft; would still depend on Pilot/MSDK for the video leg, so it cannot
  meet the wireless no-card requirement on its own.
- **USB / SD-card workflows** — explicitly excluded by requirements; kept
  only as informal manual fallback, not part of the system.
- **DJI Dock + hosted FlightHub 2** — fully autonomous but wrong hardware
  class and cost for controller-based airport inspections, and hosted cloud
  conflicts with the offline constraint.

## Rationale

The Cloud API is DJI's intended mechanism for integrating a third-party
platform *alongside* Pilot 2 rather than replacing it, and it is transport-
agnostic: "cloud" is any reachable HTTPS/MQTTS endpoint, including a laptop
on the same LAN. It is the only option that simultaneously satisfies
wireless, offline, no-flight-app, and full-quality-media. DJI ships an
official open-source reference platform (DJI Cloud API Demo) that de-risks
the protocol work and validates the hardware chain before we write code.

## Consequences

- New infrastructure to own: a second FastAPI service, MQTT broker, object
  store, and a local PKI story (cert install on each RC).
- One-time online provisioning per controller (DJI login, app license,
  binding) — field operation is offline, but first setup is not.
- The operator stays in the loop by design: flight start and (unless
  auto-upload is enabled) media upload remain actions in Pilot 2. Remote
  autonomous launch is a Dock-only feature and out of scope.
- Multi-GB 4K video transfers at local-WiFi speed (~6–12 min per 10-min
  recording) — full quality is preserved; the cost is time, surfaced as
  upload progress in the UI.
- Mavic 2 Pro and eBee X are not covered (no Cloud API support).
- New DB tables (`wayline_dispatch`, `drone_media_file`) — migrations are
  T3 and `SPEC.md` must be updated when they land.
