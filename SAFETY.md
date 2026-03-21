# Safety and Use Limits

Osk is intended for civilian safety and group coordination, but this repository
is currently in the design stage. It does not yet provide a production-ready or
validated implementation.

## What This Means Today

- The repository currently documents intended behavior more than shipped
  behavior.
- Nothing in this repo should be treated as a verified security guarantee,
  anonymity guarantee, or operational safety certification.
- If you choose to build or test from these designs, you are responsible for
  validating the resulting system in your own environment.

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
- Mobile browsers and operating systems may retain artifacts outside the app's
  direct control.
- Local-only operation reduces some risks, but it does not remove endpoint,
  operator, or insider risk.
- Emergency-wipe design goals must be validated in implementation before being
  presented as real operational guarantees.

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
