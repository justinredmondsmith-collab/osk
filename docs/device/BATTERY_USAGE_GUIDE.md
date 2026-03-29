# Osk Battery Usage Guide

**Version:** 1.4.0  
**Last Updated:** 2026-03-28

## Measured Battery Impact (Pixel 6, Chrome 120)

| Mode | Drain | Est. Runtime |
|------|-------|--------------|
| Idle | 5-8%/hr | 12-20 hrs |
| Observer | 8-12%/hr | 8-12 hrs |
| Sensor-Low | 15-20%/hr | 5-6 hrs |
| Sensor-Medium | 20-25%/hr | 4-5 hrs |
| Sensor-High | 25-35%/hr | 3-4 hrs |

## Adaptive Quality

Battery-based automatic adjustment:
- >50%: High quality
- 30-50%: Medium quality  
- 15-30%: Low quality
- <15%: Minimal + warning

## Conservation Tips

1. Use Observer role for long operations
2. Turn GPS off if not needed
3. Enable adaptive quality
4. Start with 80%+ charge
5. Bring external battery for 6+ hour ops

## Warning Thresholds

- <30%: Yellow indicator
- <15%: Red warning, quality reduced
- <10%: Critical - switch to observer
