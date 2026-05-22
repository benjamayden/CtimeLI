# Manual testing guide

Run this after any change to `adapters/macos/` or before tagging a release.
Budget **5 minutes** for the core paths; the full checklist is ~15 minutes.

## Setup

```sh
cd tools/countdown
cp .env.example .env          # if you don't have one yet
```

Open a second terminal tab to watch for errors:

```sh
cd tools/countdown
# leave this tab ready — paste commands here
```

---

## 1. Basic countdown (2 min)

```sh
./run 0.1     # ~6 second timer — good for quick checks
```

**Watch for:**
- [ ] A coloured stroke appears around every display, full perimeter
- [ ] Stroke shrinks clockwise as time passes
- [ ] HUD in the top-right shows `6s … 5s … 4s …`
- [ ] Stroke blends to red in the final second
- [ ] At zero: stroke and HUD disappear cleanly, terminal returns

**Failure signs:** overlay flickers, stroke jumps, terminal hangs after zero.

---

## 2. Edge glow

```sh
./run 3       # 3-minute timer — glow starts immediately (window is 2 min)
```

**Watch for:**
- [ ] Within the first 10 seconds a soft glow blooms inward from the screen edges
- [ ] Glow deepens (thicker) as zero approaches
- [ ] Glow is gone after the timer ends

---

## 3. Window wiggle

```sh
./run 0.05    # ~3 second timer — the whole thing is the wiggle window
```

Focus a normal window (e.g. TextEdit or Notes) before running.

**Watch for:**
- [ ] The frontmost window oscillates left/right for the ~3 seconds
- [ ] At zero the window snaps back **exactly** to where it started
- [ ] Your terminal (the launcher) is never wiggled

---

## 4. Finish button

```sh
./run 5       # 5-minute timer
```

Click the **Finish** button in the HUD within the first few seconds.

**Watch for:**
- [ ] Session ends immediately (overlay gone, terminal returns)

---

## 5. Block-on-end — core path

```sh
./run 0.1 --block-on-end
```

**Watch for:**
- [ ] At zero: stroke/HUD hide, every screen covered by a dark "It's time to stop." overlay
- [ ] Clicking in the first ~0.6 s does nothing (dismiss lockout)
- [ ] After the lockout, clicking anywhere / pressing Return / pressing Escape dismisses it
- [ ] Terminal prints `Block end: minimized N windows.` (or similar)
- [ ] Windows are minimized (check the Dock)
- [ ] Terminal gains focus after cleanup

**Also test Ctrl+C path:**

```sh
./run 0.1 --block-on-end
```
Wait for the stop overlay, then press **Ctrl+C** in the terminal tab.

- [ ] Overlay disappears
- [ ] Windows still get tidied (Ctrl+C during block must not skip the tidy)
- [ ] Terminal exits cleanly

---

## 6. Block-on-end — hide a specific app

Add to your `.env` (or pass inline):

```sh
BLOCK_END_HIDE=safari ./run 0.1 --block-on-end
```

Open Safari first. After dismissing the overlay:

- [ ] Safari is hidden (not minimised — no Dock tile bounce, just gone)
- [ ] Other foreground apps are minimised (default action)

---

## 7. Watch mode — quick add

```sh
./run watch
```

At the prompt, type `1` and press Enter.

**Watch for:**
- [ ] A 1-minute countdown starts (stroke appears)
- [ ] HUD shows `1m 0s` counting down
- [ ] Type `2` while running — existing timer replaced by a 2-minute one
- [ ] Type `q` — clean exit, terminal restored, no leftover overlays

---

## 8. Watch mode — calendar auto-start (requires a real event)

Create a calendar event starting in the next 5–8 minutes (so the 7-minute
block window fires immediately).

```sh
./run watch
```

**Watch for:**
- [ ] Within ~15 seconds: `Countdown → HH:MM:SS (Nm remaining)` printed
- [ ] Stroke is **green** (calendar session colour)
- [ ] HUD shows `Nm Ns · HH:MM` (event time suffix)

---

## 9. Multi-monitor

Attach a second display (or use a TV via HDMI/USB-C), then:

```sh
./run 0.1 --block-on-end
```

**Watch for:**
- [ ] Stroke on **both** displays
- [ ] HUD on **both** displays
- [ ] Stop overlay covers **both** displays at zero

---

## 10. Graceful degradation

**Revoke Accessibility permission:**
System Settings → Privacy & Security → Accessibility → remove Terminal/Python.

```sh
./run 0.05
```

- [ ] One warning printed: `Shake disabled: …`
- [ ] Timer still runs; everything except the wiggle works

Restore permission afterwards.

---

## 11. Block-end app manifest (numbered indices)

Run after any change to `block_executor.py`, `app_control.py`, `cli.py apps`,
`domain/manifest.py`, or `domain/blockend.py`. Budget **3 minutes**.

### 11a. Generate the app list

Open two or three regular GUI apps (e.g. Safari, Notes, TextEdit) **before**
running:

```sh
./run apps
```

**Watch for:**
- [ ] Numbered table prints: index, display name, bundle ID
- [ ] Footer shows copy-paste hint: `BLOCK_END_QUIT=1,2,3` (example indices)
- [ ] `tools/countdown/apps.manifest` created (or updated) next to `.env`
- [ ] Re-running `./run apps` overwrites the manifest (indices may shift)

**Failure signs:** empty table with apps visibly running; manifest missing; crash.

### 11b. Block-on-end via numeric index

Pick an index from §11a for an app that is **not** your terminal (e.g. Notes = `2`).

```sh
BLOCK_END_QUIT=2 ./run 0.1 --block-on-end
```

Focus the target app before the timer ends.

**Watch for:**
- [ ] At zero: stop overlay → dismiss → terminal prints `Block end: quit 1 app.`
- [ ] The app matching index `2` in the current manifest is quit/hidden/minimised
- [ ] Terminal regains focus after cleanup

### 11c. Stale index warning

```sh
BLOCK_END_QUIT=99 ./run 0.1 --block-on-end
```

**Watch for:**
- [ ] One startup warning naming index `99` and suggesting `./run apps`
- [ ] Timer still runs; no crash

### 11d. Legacy display-name config (backward compat)

Confirm §6 still works — typed names must not regress:

```sh
BLOCK_END_HIDE=safari ./run 0.1 --block-on-end
```

Open Safari first.

**Watch for:**
- [ ] Safari hidden via display-name/alias match (same as before §11)
- [ ] Other foreground apps minimised (default)

### 11e. Mixed numeric + legacy

With a valid manifest and Safari running:

```sh
BLOCK_END_HIDE=1 BLOCK_END_QUIT=safari ./run 0.1 --block-on-end
```

**Watch for:**
- [ ] Both selectors applied — one app hidden by index, Safari quit by name
- [ ] Terminal summary reflects both actions

---

## Quick smoke (30 seconds)

If you only have time for one check:

```sh
./run 0.1 --block-on-end
```

Confirm: stroke appears → shrinks → stop overlay covers both displays → click dismisses → terminal says `Block end: minimized N windows.` → windows minimised → done.

That single run exercises the stroke, the HUD, zero detection, the stop overlay, and the window tidy.
