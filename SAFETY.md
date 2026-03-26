# Safety and Use Limits

Osk is intended for civilian safety and group coordination, but this repository
is currently in the implementation-and-validation stage. It does not yet
provide a production-ready or fully validated implementation.

## What This Means Today

- The repository currently documents intended behavior more than shipped
  behavior.
- Nothing in this repo should be treated as a verified security guarantee,
  anonymity guarantee, or operational safety certification.
- If you choose to build or test from these designs, you are responsible for
  validating the resulting system in your own environment.

The proposed first-release boundary is documented in
[`docs/release/1.0.0-definition.md`](docs/release/1.0.0-definition.md). That
document narrows launch scope, but it does **not** override the non-guarantees
below unless the repo later adds explicit validation and updated claims.

## Non-Guarantees

Osk should not be described as guaranteeing:

- Anonymity
- Protection against a compromised member device
- Protection against a compromised coordinator laptop
- Perfect deletion from browsers, phones, operating systems, or hardware
- Resistance to all network monitoring or physical surveillance
- Error-free AI transcription, vision analysis, or alerting

## Trust and Threat Boundaries

- Anyone who legitimately joins an operation may still record, relay, or misuse
  information they can see.
- The current join model is intentionally low-friction and shared-token based.
  If the operation QR code or join token is leaked, relayed, or copied,
  unauthorized rejoin remains possible until the token is rotated.
- Mobile browsers and operating systems may retain artifacts outside the app's
  direct control.
- Local-only operation reduces some risks, but it does not remove endpoint,
  operator, or insider risk.
- Compromise of the coordinator host should be treated as catastrophic for the
  current release boundary. The coordinator host stores local session files,
  runtime state, TLS material, and controls privileged operations.
- Emergency-wipe design goals must be validated in implementation before being
  presented as real operational guarantees.

## Release-Limit Posture For 1.0.0

For the bounded `1.0.0` release target:

- Connected-browser wipe behavior may be validated on the supported Chromium
  path, but disconnected browsers remain outside that live broadcast guarantee.
- Browser history, operating-system caches, and other endpoint artifacts remain
  outside Osk's direct control.
- Preserved evidence may be integrity-verified on export, but confidentiality
  after export depends on operator handling and storage discipline.
- The coordinator host remains the highest-trust machine in the system; Osk
  does not claim to protect against a compromised coordinator host.

## Intended Use

Osk is intended to help groups share situational awareness and coordinate more
effectively. It is not a substitute for:

- Emergency services
- Medical judgment
- Legal advice
- Formal incident command systems
- Independent operational security practices

## Misuse

The project is not intended for stalking, unlawful surveillance, targeted
harassment, or rights-abusing monitoring. Public documentation and future
implementation work should be reviewed with that misuse risk in mind.
