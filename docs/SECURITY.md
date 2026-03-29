# Osk Security Documentation

**Version:** 2.0.0  
**Date:** 2026-03-28  
**Classification:** Public

---

## Security Model

Osk is designed for high-stakes civilian coordination. This document describes:

1. What security Osk provides
2. What security Osk does NOT provide
3. How to deploy securely
4. How to verify security claims

---

## What Osk Provides

### Authentication & Authorization

| Feature | Implementation | Version |
|---------|----------------|---------|
| Token-based auth | `TokenLifecycleManager` | 2.0.0 |
| Automatic rotation | Every 30 minutes | 2.0.0 |
| Device fingerprinting | Session binding | 2.0.0 |
| Session limits | 5 max per user | 2.0.0 |
| Shorter sessions | 4hr operator, 2hr member | 2.0.0 |

```python
# Token security characteristics
SECURITY_2_0_DEFAULTS = {
    "operator_session_hours": 4,      # Reduced from 24
    "member_session_hours": 2,         # Reduced from 12
    "token_rotation_minutes": 30,      # New: automatic rotation
    "rotation_grace_minutes": 5,       # Grace period for rotation
    "max_concurrent_sessions": 5,      # Per-user limit
}
```

### Encryption

| Layer | Implementation | Status |
|-------|----------------|--------|
| Transport | TLS 1.3 (mandatory) | ✅ Always on |
| At rest | LUKS or directory | ✅ Configurable |
| Evidence | SHA-256 integrity | ✅ All exports |

### Audit Logging

| Event | Logged | Location |
|-------|--------|----------|
| Token creation | ✅ | Security audit log |
| Token rotation | ✅ | Security audit log |
| Failed auth | ✅ | Security audit log |
| Wipe initiation | ✅ | Wipe verification log |
| Wipe confirmation | ✅ | Wipe verification log |
| Evidence export | ✅ | Operation audit |

### Wipe Verification

```bash
$ osk drill wipe

Wipe Readiness Check
====================
✅ Hub can stop cleanly
✅ 8 members connected (will receive wipe signal)
⚠️  2 members disconnected (need follow-up)
⚠️  3 evidence files pending export

Recommendation: Export evidence before wipe
```

Wipe events include:
- Member acknowledgment tracking
- Cleanup verification
- Residual risk assessment
- Failed wipe detection

---

## What Osk Does NOT Provide

### Critical Limitations

| Claim | Status | Explanation |
|-------|--------|-------------|
| **Anonymity** | ❌ NOT PROVIDED | Network traffic is observable |
| **Endpoint protection** | ❌ NOT PROVIDED | Compromised devices = catastrophic |
| **Perfect deletion** | ❌ NOT PROVIDED | OS/browser artifacts may remain |
| **Forensic wipe** | ❌ NOT PROVIDED | No specialized forensic verification |
| **Tamper-proof** | ⚠️ LIMITED | SHA-256 detects tampering, not prevent |

### Network Observability

```
ATTACKER CAN SEE:
├── That Osk hub exists (port scanning)
├── Member IP addresses (network sniffing)
├── Traffic timing patterns
├── Approximate data volume
└── (With TLS) NOT message contents

ATTACKER CANNOT SEE (with TLS):
├── Observation content
├── Member identities
├── Coordinator commands
├── Evidence contents
```

### Endpoint Security

**If a member device is compromised:**
- Attacker sees what member sees
- Attacker can impersonate member
- Attacker may access cached data
- Attacker knows hub location

**Mitigations:**
- Shorter session timeouts
- Token rotation
- Device fingerprinting
- Wipe on compromise detection

### Residual Data

After wipe, these MAY remain:
- Browser cache/history
- OS-level network logs
- DNS cache
- Screenshots/recordings outside Osk
- Memory forensics (until overwritten)

---

## Deployment Security

### Coordinator Machine

#### Physical Security

- Keep coordinator laptop physically secure
- Use full-disk encryption (LUKS)
- Lock screen when unattended
- Secure boot if available

#### Network Security

```bash
# Use dedicated WiFi (not shared with members)
osk hotspot up --isolated

# Or use Ethernet when available
# Disable WiFi if using wired

# Firewall rules (optional)
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --add-port=8443/tcp --permanent
sudo firewall-cmd --add-port=8444/tcp --permanent
```

#### Evidence Storage

```toml
# ~/.config/osk/config.toml
[storage]
backend = "luks"  # More secure than directory
luks_volume_size_gb = 10

[evidence]
storage_path = "/var/lib/osk/evidence"
retention_days = 90
```

### Member Devices

#### Security Requirements

| Requirement | Why |
|-------------|-----|
| Chromium browser | Best WebRTC security |
| Screen lock | Prevent unauthorized access |
| Auto-lock timer | Reduce exposure window |
| No untrusted apps | Reduce compromise risk |

#### Pre-Operation Checklist

- [ ] Browser is up to date
- [ ] OS is up to date
- [ ] No untrusted browser extensions
- [ ] Screen lock enabled
- [ ] Device encrypted (if available)

### Operational Security

#### Before Operation

```bash
# Verify system state
osk doctor
osk drill install

# Check for unauthorized access
last  # Who logged in recently
w     # Who is currently logged in

# Verify evidence storage
osk evidence status
```

#### During Operation

```bash
# Monitor connected members
osk status --json | jq '.members'

# Watch for anomalies
osk logs --tail 100 | grep -i "error\|warning\|fail"

# Regular checkpoints
osk aar export --output checkpoint-$(date +%H%M).zip
```

#### After Operation

```bash
# Verify wipe readiness
osk drill wipe

# Export final AAR
osk aar export --output final-aar.zip
osk aar verify final-aar.zip

# Execute wipe
osk wipe --yes

# Verify stopped
osk status  # Should show "No operation running"

# Follow up with disconnected members
```

---

## Security Verification

### Automated Tests

```bash
# Run security tests
python -m pytest tests/test_security_hardening.py -v

# 23 tests covering:
# - Token lifecycle
# - Rotation behavior
# - Session limits
# - Wipe verification
# - Audit logging
```

### Manual Verification

#### Token Security

```bash
# Check token rotation is working
osk logs | grep "token.*rotated"

# Verify session limits
# Try to create 6+ sessions from same user
# 6th should be rejected
```

#### Wipe Verification

```bash
# Check wipe logs
osk logs | grep "wipe"

# Verify residual risk logged
grep "residual_risk" ~/.local/share/osk/wipe.log
```

#### Audit Trail

```bash
# Check security events
osk audit --type security --last 24h

# Verify failed auth logged
# (Try wrong password, check logs)
```

---

## Threat Model

### Assets to Protect

1. **Operational data** - Observations, findings, intelligence
2. **Member identities** - Who participated
3. **Coordinator identity** - Who directed operation
4. **Evidence integrity** - Tamper-proof records
5. **Operational patterns** - When/where operations occur

### Threats Addressed

| Threat | Mitigation | Status |
|--------|------------|--------|
| Eavesdropping | TLS 1.3 | ✅ Mitigated |
| Token theft | Rotation + fingerprinting | ✅ Mitigated |
| Session hijacking | Short timeouts | ✅ Mitigated |
| Evidence tampering | SHA-256 integrity | ✅ Mitigated |
| Unauthorized access | Token auth | ✅ Mitigated |
| Wipe failures | Verification logging | ✅ Mitigated |

### Threats NOT Addressed

| Threat | Why Not | Mitigation Advice |
|--------|---------|-------------------|
| Traffic analysis | Out of scope | Use Tor/VPN if needed |
| Endpoint compromise | Out of scope | Endpoint hardening |
| Physical seizure | Out of scope | LUKS + rapid wipe |
| Supply chain | Out of scope | Verify pip hashes |
| Social engineering | Out of scope | Training |

---

## Incident Response

### Suspected Compromise

```bash
# 1. Immediate assessment
osk status
osk logs --tail 1000

# 2. Check for unauthorized members
osk status --json | jq '.members[] | select(.name | contains("suspicious"))'

# 3. If confirmed compromise:
osk wipe --yes  # Emergency wipe

# 4. Document incident
# Note time, affected members, actions taken
```

### Evidence Tampering

```bash
# If AAR verification fails:
osk aar verify suspicious-export.zip

# Do NOT use failed export for legal proceedings
# Re-export from hub if operation still running
# Document the failure
```

### Coordinator Machine Compromised

1. **Immediate:** Execute `osk wipe --yes`
2. **Disconnect:** Remove from network
3. **Document:** What was accessed
4. **Notify:** All operation participants
5. **Rebuild:** Fresh OS install before next operation

---

## Security Checklist

### Pre-Deployment

- [ ] `osk doctor` passes all checks
- [ ] LUKS encryption configured (not just directory)
- [ ] TLS certificates valid
- [ ] Firewall rules reviewed
- [ ] Physical security plan in place

### Pre-Operation

- [ ] Member device security verified
- [ ] Coordinator machine locked down
- [ ] Evidence storage ready
- [ ] Wipe procedure reviewed
- [ ] Backup communication plan ready

### During Operation

- [ ] Regular checkpoint exports
- [ ] Monitor for anomalies
- [ ] Verify member identities
- [ ] Secure coordinator laptop

### Post-Operation

- [ ] Evidence exported and verified
- [ ] Wipe executed successfully
- [ ] Follow-up completed for disconnected members
- [ ] AAR archived securely

---

## Reporting Security Issues

**Do NOT open public issues for security vulnerabilities.**

Instead:
1. Email: justin.redmond.smith@gmail.com
2. Subject: "[OSK SECURITY] Brief description"
3. Include:
   - Affected version
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

**Response time:**
- Acknowledgment: Within 48 hours
- Initial assessment: Within 1 week
- Fix timeline: Depends on severity

---

## References

- [Safety Guide](../SAFETY.md) - Operational security practices
- [Install Guide](INSTALL_GUIDE.md) - Secure deployment
- [Supported Profiles](SUPPORTED_PROFILES.md) - Validated configurations
- [AAR Guide](AAR_GUIDE.md) - Evidence handling

---

**Security is a process, not a product.**

Regularly review this document and update your practices as threats evolve.

**Version:** 2.0.0  
**Last Reviewed:** 2026-03-28
