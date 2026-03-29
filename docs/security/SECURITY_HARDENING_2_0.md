# Security Hardening for Release 2.0

**Version:** 2.0  
**Status:** Implementation Checklist

## Hardening Areas

### 1. Token Lifecycle

- [ ] Shorter session timeouts (Operator: 4hr, Member: 2hr)
- [ ] Token rotation every 30 minutes
- [ ] Device binding with fingerprinting

### 2. Key Handling

- [ ] Per-operation signing keys
- [ ] Weekly TLS certificate rotation
- [ ] Audit logging for key access

### 3. Wipe Verification

- [ ] Pre-wipe checklist
- [ ] Member acknowledgment tracking
- [ ] Residual risk documentation
- [ ] Optional forensic overwrite mode

### 4. Privacy Claims Audit

Verify documentation matches implementation:
- [ ] Data retention (30-day default)
- [ ] Location precision reduction
- [ ] Member pseudonymization in exports
- [ ] Wipe "best effort" language

## Non-Goals

- Hardware security modules (HSM)
- End-to-end encryption
- Blockchain audit trails
- Anonymous credentials

## Success Criteria

| Criterion | Target |
|-----------|--------|
| Session timeout | 100% enforcement |
| Wipe success | 100% for connected members |
| Privacy truthfulness | 0 false claims |
