# LinkedIn Post — Ultra Trail Tarahumara Tracker

**Date:** 2026-05-03
**Status:** Ready to publish
**Author:** Emmanuel Diaz

## What's in this folder

| File | Purpose |
|------|---------|
| `post.txt` | **The actual post copy.** Open it, select all, paste into LinkedIn. |
| `slide5.png` | Final slide 5 (stack list), 1080×1080, drop into the carousel as slide 5. |
| `slide5-generator.py` | Python script that made slide5.png — re-run if you want to tweak it. |
| `README.md` | This document — design rationale + screenshot guide for slides 1–4. |

## TL;DR — what to do

1. Capture screenshots for slides 1–4 from the live dashboard (see [Production checklist](#production-checklist))
2. Crop each to 1080×1080 to match `slide5.png`
3. Open LinkedIn, click "Start a post" → upload as 5-slide carousel in this order: 1, 2, 3, 4, slide5.png
4. Paste the [post copy](#post-copy) below the carousel
5. Publish

## Goal

Personal milestone share to existing LinkedIn network. Showcase the trail running training app I built, with the AI coach as the centerpiece feature. Race and app run side-by-side. No specific call to action.

## Audience

Existing LinkedIn network: mixed finance colleagues, friends, some tech contacts. Not aimed at recruiters and not aimed at the AI/dev crowd specifically.

## Tone

Confident-builder. Direct, no hedging. "I made this, here's what it does."

Must sound human, not AI:
- No em-dashes used as stylistic flair
- No "production-ready," "grounded in," "leveraging"
- No over-polished tricolons
- Contractions OK
- Specific concrete details over abstract claims

## Format

Carousel of 5 slides plus medium-length post copy (~175 words) below it.

Constraints:
- No live URL of the deployed dashboard
- No personal photos, no training photos
- Race context conveyed through copy, not imagery

## Carousel slides

### Slide 1 — Cover
Full dashboard screenshot with the AI coach drawer open. Shows the whole app and the coach in one shot. The first thing the viewer sees is "training tracker + AI assistant."

### Slide 2 — Week detail
Plan vs actual view, weekly compliance score, at least one alert firing (HR drift, volume spike, or similar). Establishes the analytical substance of the app.

### Slide 3 — Activity feed
Live Garmin data: running, strength, trail run with route polyline visible. Establishes that this is real data, not a demo.

### Slide 4 — Coach hero
Zoomed screenshot of an actual Q&A turn with the AI coach. Pick one where the coach references concrete training data (HR zones, recent workouts, sleep, etc.).

Slide 4 caption text:
> Fed it real trail-running coaching material, professional nutrition guides, and my own Garmin health history. Not just another chatbot.

### Slide 5 — Stack
Pure text on a clean background:

```
Python · FastAPI · Postgres · Next.js · Garmin Connect · Anthropic Claude · Built solo with Claude Code
```

Match the dashboard's typographic style if possible (IBM Plex Mono).

## Post copy

See `post.txt` in this folder for the canonical, copy-pasteable version. Reproduced here for review:

```
First real web app I've built. First Garmin API integration. First time I've worked with an LLM.

All in one project: a training tracker for my first ultra. In 5 months I'm running 59km through the Sierra Tarahumara, with 2,400m of vertical gain. Built it to keep me honest.

It syncs every workout from my Garmin, compares what I actually did against the 30-week plan, and gives me a weekly compliance score. Six rules watch for things like HR drift, volume spikes, or skipped long runs and call them out before things go sideways.

The piece I'm most proud of is the AI coach. I fed it actual trail-running coaching material, professional nutrition guides, and my own Garmin health history. So when I ask it whether I should push my long run this Saturday or hold back, it pulls from my last few weeks of HR, sleep, and stress data and gives me an answer that fits my body, not the average runner. It's not just another chatbot.

About 30 days from idea to production. Solo build. It tracks me every day until October 2.

#BuildInPublic #AI #Python #UltraTrail #ClaudeCode
```

Word count: ~205. The "firsts" opening sits above the LinkedIn "see more" fold and creates an immediate hook for the audience to swipe the carousel.

## Hashtags

Five tags, mix of broad and niche per LinkedIn 2026 best practice (3–5 is the sweet spot; more triggers the spam filter):

```
#BuildInPublic #AI #Python #UltraTrail #ClaudeCode
```

Rationale:
- `#BuildInPublic` — niche dev/founder community, recruiters and indie tech folks watch it
- `#AI` — broad algorithm-categorization signal
- `#Python` — searchable by tech recruiters scanning for stack
- `#UltraTrail` — race-authenticity tag, keeps the post tonally honest
- `#ClaudeCode` — niche but specific, surfaces to Anthropic-adjacent crowd

PascalCase used throughout (2026 standard, screen-reader accessible). Tags placed at the end of the post, not inline.

## Production checklist

### Slide 1 — Cover
- [ ] Open the dashboard, click the coach drawer button to expand it.
- [ ] Make sure the countdown widget (top right) is visible.
- [ ] Use the current week (one with real synced activities) so the dashboard looks alive.
- [ ] Capture: `Cmd+Shift+4`, then `Space`, then click the browser window to grab the whole canvas without browser chrome.

### Slide 2 — Week detail
- [ ] Drill into a single week's detail view (accordion expanded).
- [ ] Pick a week with at least one active alert (HR drift, volume spike, etc.). Alerts are the visual hook.
- [ ] Crop tightly to the week card; exclude the rest of the dashboard.

### Slide 3 — Activity feed
- [ ] Inside a week, capture the activity list with a visible route polyline.
- [ ] Pick a week with at least one trail run (the curvy GPS line proves "real outdoor activity").
- [ ] Bonus: a week that also has a strength activity, to show variety.

### Slide 4 — Coach hero
- [ ] Open the coach drawer. Ask something specific and data-grounded:
  > "Should I push my long run this Saturday or hold back?"
- [ ] Wait for the full reply. Crop to one Q&A turn (your question + the coach's answer).
- [ ] The answer should reference real metrics (HR zones, sleep, recent workouts) — that's what sells "not just another chatbot."

### Slide 5 — Stack
Already done. Use `slide5.png` as-is. To regenerate or tweak:
```bash
cd /Users/emmanueldiaz/Documents/Main_Brain/personal_health/running
source venv/bin/activate
python docs/linkedin-post/slide5-generator.py
```

### General
- [ ] Crop all 5 slides to **1080×1080** (square) for visual consistency.
- [ ] Order the carousel: 1, 2, 3, 4, 5 (slide5.png last).
- [ ] Paste the post copy from the [Post copy](#post-copy) section below the carousel.

## Race facts (for accuracy)

- Race: Ultra Trail Tarahumara
- Distance: 59 km
- Vertical gain: 2,400 m
- Date: October 2, 2026
- Location: Sierra Tarahumara

## Out of scope

- Long-form story version (300+ words, journey-led)
- Video walkthrough
- Public link to the live app
- Recruiter-aimed framing
