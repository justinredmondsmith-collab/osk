# Real Device Test - Quickstart (5 Minutes)

**Test your Android phone with Osk right now**

---

## Step 1: Start Osk on Your Laptop

```bash
osk start --fresh "Phone Test"
osk dashboard
```

**Note these values:**
- IP Address: `___________` (from `hostname -I`)
- Dashboard Code: `___________`

---

## Step 2: Prepare Your Phone

1. **Connect to same WiFi** as your laptop
2. **Check battery:** Settings → Battery → Note %: `____%`
3. **Open Chrome** (not other browsers)

---

## Step 3: Join the Operation

1. **Navigate to:**
   ```
   https://[YOUR-IP]:8444/join
   ```
   (Replace [YOUR-IP] with your laptop's IP)

2. **Handle SSL warning:**
   - Tap "Advanced" → "Proceed to..."

3. **Enter dashboard code** from Step 1

4. **Select role:** "Sensor"

5. **Enter name:** "MyPhone" (or your name)

6. **Grant permissions:**
   - Camera: Allow
   - Microphone: Allow  
   - Location: Allow

---

## Step 4: Verify Connection

On laptop:
```bash
osk members
```

You should see your phone listed!

---

## Step 5: Monitor (10 Minutes)

**On laptop:**
- Open dashboard: `https://127.0.0.1:8444/coordinator`
- Login with dashboard code
- Watch your phone appear

**On phone:**
- Keep screen on
- Keep Chrome open
- Note any issues

**Record:**
- Start time: `____:____`
- Start battery: `____%`

---

## Step 6: Check Battery Drain

After 10 minutes:
- Phone battery: `____%`
- Drain: `(start - end) × 6 = ____%/hour`

**Target:** <25%/hour for 10-minute test

---

## Step 7: Stop Test

```bash
osk stop
```

Close Chrome on phone.

---

## Results Checklist

- [ ] Phone joined successfully
- [ ] Permissions granted
- [ ] Member visible in dashboard
- [ ] No crashes/errors
- [ ] Battery drain measured

**If all checked:** ✅ PASSED

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Can't load page | Check same WiFi, try laptop hotspot |
| SSL error | Expected - tap "Proceed anyway" |
| Camera won't work | Check Chrome permissions in Settings |
| Not in member list | Refresh page, try joining again |

---

## What This Proves

✅ Your phone can connect to Osk  
✅ Permissions work correctly  
✅ Basic streaming functions  
✅ Battery impact measured  

---

## Next: Full Validation

For complete 1.1.1 validation:
1. Run 30-minute test
2. Test 2-3 phones simultaneously
3. Document results
4. See: `docs/runbooks/real-device-validation.md`
