# Osk Browser Support Matrix

**Version:** 1.4.0 Validation  
**Last Updated:** 2026-03-28  

## Overview

This document defines the supported browser matrix for Osk 1.4.0+ based on real-device validation.

## Support Tiers

### Tier 1: Fully Supported
Browsers that receive full testing and are recommended for field use.

| Browser | Minimum Version | Status | Notes |
|---------|----------------|--------|-------|
| Chrome (Android) | 120+ | ✅ Supported | Primary development target |
| Chrome (Desktop) | 120+ | ✅ Supported | Coordinator dashboard |
| Chromium (Chromebook) | 120+ | ✅ Supported | Validated on real hardware |

### Tier 2: Supported with Degradation
Browsers that work but may have reduced functionality.

| Browser | Minimum Version | Status | Known Limitations |
|---------|----------------|--------|-------------------|
| Firefox (Android) | 120+ | ⚠️ Degraded | WebRTC may have issues |
| Firefox (Desktop) | 120+ | ⚠️ Degraded | Audio capture less reliable |
| Safari (iOS) | 16+ | ⚠️ Degraded | No background audio, PWA limited |
| Safari (macOS) | 16+ | ⚠️ Degraded | Same limitations as iOS |

### Tier 3: Not Supported
Browsers that are explicitly not supported.

| Browser | Reason |
|---------|--------|
| IE 11 | No WebSocket, no ES6 |
| Edge Legacy | No longer maintained |
| Opera Mini | No WebSocket support |
| UC Browser | Inconsistent WebRTC |
| Samsung Internet < 20 | Outdated WebRTC |

## Feature Matrix by Browser

### Core Features

| Feature | Chrome | Firefox | Safari |
|---------|--------|---------|--------|
| Join flow | ✅ | ✅ | ✅ |
| WebSocket connection | ✅ | ✅ | ✅ |
| Manual reports | ✅ | ✅ | ✅ |
| Photo capture | ✅ | ✅ | ✅ |
| Audio clip capture | ✅ | ✅ | ✅ |

### Sensor Features

| Feature | Chrome | Firefox | Safari |
|---------|--------|---------|--------|
| Audio streaming | ✅ | ⚠️ | ❌ |
| Frame capture | ✅ | ✅ | ⚠️ |
| Background audio | ✅ | ⚠️ | ❌ |
| Battery API | ✅ | ❌ | ❌ |

### PWA Features

| Feature | Chrome | Firefox | Safari |
|---------|--------|---------|--------|
| Install prompt | ✅ | ❌ | ⚠️ |
| Offline shell | ✅ | ✅ | ⚠️ |
| Push notifications | ✅ | ❌ | ❌ |
| Background sync | ✅ | ❌ | ❌ |

Legend:
- ✅ Full support
- ⚠️ Partial support / known issues
- ❌ Not supported

## Validation Test Procedures

### Chrome (Primary)

1. Install Chrome on Android device
2. Run `reconnect_stress_test.html` - 100 cycles
3. Run `test_pwa_resilience.html` - offline/online tests
4. Run 30-minute sensor test with battery monitoring
5. Verify all features work as expected

**Pass Criteria:**
- Reconnect success rate >= 95%
- Battery drain < 30%/hour with sensors
- No crashes or freezes

### Firefox

1. Install Firefox on Android device
2. Run join flow
3. Test manual reports and media capture
4. Attempt sensor streaming
5. Document any issues

**Pass Criteria:**
- Join and basic features work
- Sensor features may fail gracefully
- Clear error messages for unsupported features

### Safari

1. Open Safari on iOS device
2. Test join flow
3. Test manual features only
4. Document sensor limitations
5. Test PWA install flow

**Pass Criteria:**
- Join and manual features work
- Sensor features disabled or show clear warnings
- PWA install works via "Add to Home Screen"

## Battery Impact by Browser

Measured on Pixel 6, 30-minute test:

| Browser | Mode | Battery Drain | Notes |
|---------|------|---------------|-------|
| Chrome | Idle | 5-8%/hour | Baseline |
| Chrome | Sensors | 25-35%/hour | Expected range |
| Firefox | Idle | 6-10%/hour | Slightly higher |
| Firefox | Sensors | 30-40%/hour | Less efficient |
| Safari | Idle | 5-8%/hour | Similar to Chrome |
| Safari | Sensors | N/A | Not supported |

## Known Issues

### Chrome
- None critical
- Occasional WebRTC reconnection needed

### Firefox
- Audio streaming may drop after 10+ minutes
- Reconnect success rate ~90% (vs 98% Chrome)
- Battery drain ~10% higher

### Safari
- No background audio capture (iOS restriction)
- Frame capture limited to foreground
- PWA install requires manual "Add to Home Screen"
- IndexedDB may be cleared under memory pressure

## CI Testing

Automated tests run on:

| Browser | CI Platform | Test Type |
|---------|-------------|-----------|
| Chrome | GitHub Actions | Unit + Integration |
| Chrome | Playwright | E2E |
| Firefox | Playwright | E2E (weekly) |
| Safari | Manual | Quarterly validation |

## Recommendations

### For Coordinators
- **Primary:** Use Chrome/Chromium for best experience
- **Backup:** Firefox acceptable for manual observers
- **Avoid:** Safari for sensor roles

### For Members
- **Android:** Chrome recommended, Firefox acceptable
- **iOS:** Safari only option, limited to manual features
- **Chromebook:** ChromeOS browser fully supported

## Future Work

### 2.0 Release Goals
- [ ] Improve Firefox sensor reliability to 95%
- [ ] Add Safari background audio (if iOS APIs allow)
- [ ] Automated Safari testing via BrowserStack

### Post-2.0
- [ ] Evaluate native app need based on Safari limitations
- [ ] Samsung Internet validation (popular in some regions)

## Validation Evidence

| Date | Browser | Device | Tester | Results |
|------|---------|--------|--------|---------|
| 2026-03-28 | Chrome 120 | Pixel 6 | Automated | ✅ Passed |
| 2026-03-28 | Firefox 123 | Pixel 6 | Manual | ⚠️ Acceptable |
| 2026-03-28 | Safari 17 | iPhone 14 | Manual | ⚠️ Degraded |

## References

- [Can I Use - WebRTC](https://caniuse.com/webrtc)
- [Can I Use - Service Workers](https://caniuse.com/serviceworkers)
- [Can I Use - Battery Status](https://caniuse.com/battery-status)
- [MDN - Browser Compatibility](https://developer.mozilla.org/en-US/docs/Web/API/WebRTC_API/Browser_compatibility)
