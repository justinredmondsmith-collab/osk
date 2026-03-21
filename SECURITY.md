# Security Policy

Osk is a design-stage public repository for a safety-sensitive system. Please
report security and privacy issues responsibly.

## Current Status

- This repository is currently pre-implementation.
- `main` is the only supported version.
- Some reported issues may affect design documents and planned architecture
  rather than shipped runtime code.

## How to Report

**Do not open a public GitHub issue** for anything that could materially reduce
user safety, compromise privacy, or make future exploitation easier.

Report privately to `osk-reports@proton.me`.

Include, when possible:

- A clear description of the issue
- Affected file, component, or design section
- Reproduction steps or validation steps
- Expected behavior and actual behavior
- Potential impact
- Any proposed mitigation

Use encrypted email if you believe the report itself is sensitive.

## What to Report

We especially care about:

- Data that survives when it is documented as ephemeral
- Authentication, authorization, or token-handling weaknesses
- Network exposure or unintended disclosure of operational data
- Emergency-wipe failures or gaps in wipe assumptions
- Browser, storage, or cache behavior that weakens stated privacy guarantees
- Design flaws that would create unsafe trust assumptions for users

## Out of Scope

The following are usually out of scope for private security reporting:

- General product criticism without a concrete vulnerability or design flaw
- Feature requests
- Denial-of-service concerns without a realistic exploit path
- Vulnerabilities that only exist in third-party services or hardware not
  controlled by this repository
- Reports that depend on social engineering, physical device theft, or a fully
  compromised endpoint unless the repo claims to defend against that scenario

## Disclosure Expectations

- Please give the maintainers a reasonable opportunity to assess and mitigate
  the issue before public disclosure.
- We may ask for clarification or a retest if the repository is still in a
  design-only stage.
- There is currently no bug bounty program.

## Safe Harbor

If you act in good faith, avoid privacy harm, avoid service disruption, and do
not exfiltrate data beyond what is necessary to demonstrate the issue, we will
not treat your research as hostile.

## Response Timeline

- Acknowledgment target: within 48 hours
- Initial triage target: within 7 days
- Mitigation target: depends on severity and repo maturity

## Credit

We can credit reporters in release notes or project documentation unless you
prefer to remain anonymous.

## Non-Security Issues

For non-sensitive bugs, documentation problems, and general design feedback,
use GitHub issues or discussions instead.
