# Manual testing guide

Run this after any change to `adapters/macos/` or before tagging a release.
Budget **5 minutes** for the core paths; the full checklist is ~15 minutes.

## Setup

```sh
cp .env.example .env          # if you don't have one yet
```

Open a second terminal tab to watch for errors:

```sh
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

## 3. Screen blur

**In a real countdown:**

```sh
./run 2 --block-on-end    # blur window is 30 s; glow still starts at 120 s
```

**Watch for:**
- [ ] Edge glow may appear before blur (glow window is longer)
- [ ] Desktop blur ramps only in the final ~30 s
- [ ] Stroke/glow stay visible **above** the blur; HUD Finish stays clickable
- [ ] At zero with `block_on_end`: blurred desktop shows through the stop overlay
- [ ] Click dismiss clears blur and the block screen together

Automated checklist: `./test_manual.sh blur`.

---

## 3a. Wake from sleep

```sh
./run 5 --block-on-end
```

Put the Mac to sleep for ~1 minute, then wake.

**Watch for:**
- [ ] Timer ends on wake — **no** stop overlay (sleep is not hyperfocus)
- [ ] Terminal reports the session ended after sleep
- [ ] In watch mode with a calendar event: event is not re-triggered; call link
      opens if applicable

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
- [ ] Cursor is hidden while the overlay is up; reappears immediately on dismissal
- [ ] Clicking in the first ~0.6 s does nothing (dismiss lockout)
- [ ] After the lockout, clicking anywhere / pressing Return / pressing Escape dismisses it
- [ ] Terminal prints `Block end: hid other apps, minimized focused window.`
- [ ] Other apps are hidden; the focused app is minimized into the Dock
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

## 6. Watch mode — menu bar

```sh
./run watch
```

The terminal prints a status line and returns. Click the timer icon in the menu bar.

**Watch for:**
- [ ] Menu bar icon visible after launch; terminal prompt returns
- [ ] Click icon → menu with **Start timer…** and **Quit watch mode**
- [ ] **Start timer…** → enter `1` → OK → 1-minute countdown (stroke + HUD)
- [ ] Icon title shows remaining time (e.g. `1m 0s`) while running
- [ ] **Add** extends a pure manual session; **Add** disabled during green/orange calendar/hard-stop
- [ ] Close the launch terminal — watch keeps running; icon still visible
- [ ] **Quit watch mode** — icon disappears, process exits, no leftover overlays

---

## 7. Watch mode — calendar auto-start (requires a real event)

Create a calendar event starting in the next 5–8 minutes (so the 7-minute
block window fires immediately).

```sh
./run watch
```

**Watch for:**
- [ ] Within ~15 seconds: `CtimeLI → HH:MM:SS (Nm remaining)` printed
- [ ] Stroke is **green** (calendar session colour)
- [ ] HUD shows `Nm Ns · HH:MM` (event time suffix)

---

## 8. Multi-monitor

Attach a second display (or use a TV via HDMI/USB-C), then:

```sh
./run 0.1 --block-on-end
```

**Watch for:**
- [ ] Stroke on **both** displays
- [ ] HUD on **both** displays
- [ ] Stop overlay covers **both** displays at zero

---

## 9. Graceful degradation

**Revoke Accessibility permission:**
System Settings → Privacy & Security → Accessibility → remove Terminal/Python.

```sh
./run 0.1 --block-on-end
```

Open a few apps, dismiss the stop overlay.

- [ ] One warning printed about Accessibility / workspace tidy
- [ ] Timer and overlay still work; tidy no-ops

Restore permission afterwards.

---

## 10. App manifest (`./run apps`) — debug only

The manifest is **not** loaded at startup; block-end tidy no longer uses per-app
indices. This command is a debug helper to list running GUI apps and write
`apps.manifest` for reference.

Run after any change to `app_control.py` or `cli.py apps`. Budget **1 minute**.

Open two or three regular GUI apps (e.g. Safari, Notes, TextEdit) **before**
running:

```sh
./run apps
```

**Watch for:**
- [ ] Numbered table prints: index, display name, bundle ID
- [ ] `apps.manifest` created (or updated) next to `.env`
- [ ] Re-running `./run apps` overwrites the manifest (indices may shift)

**Failure signs:** empty table with apps visibly running; manifest missing; crash.

---

## Quick smoke (30 seconds)

If you only have time for one check:

```sh
./run 0.1 --block-on-end
```

Confirm: stroke appears → shrinks → stop overlay covers both displays → click dismisses → terminal says `Block end: hid other apps, minimized focused window.` → other apps hidden, focused app minimized → done.

That single run exercises the stroke, the HUD, zero detection, the stop overlay, and the window tidy.
