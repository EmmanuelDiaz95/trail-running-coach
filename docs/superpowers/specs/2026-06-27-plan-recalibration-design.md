# Plan Recalibration — Design Reference

**Date:** 2026-06-27
**Status:** Logic executed manually this session; captured here as the reference spec for a
future Phase 4 coach-agent capability ("recalibrate plan from current fitness").

## Problem

The 30-week plan assumes you follow it. When an athlete falls behind (illness, travel, life),
the forward weeks become detached from reality — ramping toward targets built off a fitness
level the athlete no longer has. Forcing the original ramp from a regressed base is the classic
injury setup. The plan needs to be **rebuilt from where the athlete actually is**, on demand.

## Inputs

1. **Current fitness** — trailing 4-week actuals from `week_snapshots` / Garmin: weekly distance,
   long run, vert, gym, consistency. (4-week window matches `knowledge.json.trends.lookback_weeks`.)
2. **Peak achieved** — best recent block, to gauge residual fitness (re-gaining is faster than
   building fresh, so the ramp may exceed a cold-start 10%).
3. **Athlete benchmarks** (`athlete.json`) — race PR (distance/vert/time), baseline weekly km,
   training altitude.
4. **Race demands** (`athlete.json.race`) — distance, vert, date → weeks remaining.
5. **Coach rules** (`knowledge.json`, `tracker/config.py`):
   - Max weekly volume increase: **10%** (nudge to ~10–13% when rebuilding lost fitness).
   - ACWR target **0.8–1.3** (acute = this week, chronic = 4-wk avg).
   - Recovery weeks: **−25–30%** volume.
   - Long-run ratio info-alert at 30% of weekly volume (expected to exceed in ultra prep — informational only).

## Algorithm

```
weeks_left = weeks between current week and race week
chronic    = mean(last 4 weeks actual distance)
1. Set week+1 starting distance ≈ chronic × (1.0–1.25)   # ACWR-safe first step
2. Build blocks of 3 weeks at +~10–13%/wk, then 1 recovery week at −25–30%
3. Anchor PEAK long run to the athlete's proven race-PR distance (here: 32km vs 33km PR),
   placed ~2 weeks before race
4. Build vert toward ~80% of race vert at peak (weekly vert need not exceed race total)
5. Taper: final 2–3 weeks, −25%/wk, drop intensity volume, keep some sharpening
6. Race week: minimal volume + the race
```

Difficulty knob (conservative / **medium** / aggressive) scales the ramp rate and peak targets.
Medium = race-ready while prioritizing staying healthy.

## This session's instance (2026-06-27, weeks 18–30)

- Current: ~16–18 km/wk, 6–8 km long runs (6 weeks reduced from a 46 km peak in mid-May).
- Race: UTT 59 km / 2400 m vert, Oct 2 2026 (~14 weeks out).
- Output peak: **48 km/wk, 32 km long run, 1900 m vert** (week 27), 3-week taper.
- Written to Postgres via `db.update_plan_field`, source `recalibration`, every field logged in
  `plan_changes` (reversible). 50 field changes across weeks 18–30. Week 17 (in progress) untouched.

## To productize (Phase 4)

- Module `coach/recalibration.py`: `recalibrate(profile_id, difficulty) -> list[WeekPlan]` implementing
  the algorithm above, reading the same inputs.
- Expose via coach chat ("I've fallen behind, rebuild my plan") + a confirm step showing the diff
  before writing through the existing audit-logged path.
- Reuse `generate_adjustments` signals as triggers (sustained low compliance → suggest recalibration).
