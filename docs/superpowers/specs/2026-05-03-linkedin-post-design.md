# LinkedIn Post Design — Ultra Trail Tarahumara Tracker

**Date:** 2026-05-03
**Status:** Approved design
**Author:** Emmanuel Diaz

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

```
In 5 months I'm running 59km through the Sierra Tarahumara, with 2,400m of vertical gain. I built my own training tracker to keep me honest.

It syncs every workout from my Garmin, compares what I actually did against the 30-week plan, and gives me a weekly compliance score. Six rules watch for things like HR drift, volume spikes, or skipped long runs and call them out before things go sideways.

The piece I'm most proud of is the AI coach. I fed it actual trail-running coaching material, professional nutrition guides, and my own Garmin health history. So when I ask it whether I should push my long run this Saturday or hold back, it pulls from my last few weeks of HR, sleep, and stress data and gives me an answer that fits my body, not the average runner. It's not just another chatbot.

About 30 days from idea to production. Solo build. It tracks me every day until October 2.

#UltraTrail #BuildInPublic
```

Word count: ~175. First line fits above the LinkedIn "see more" fold.

## Hashtags

Two only: `#UltraTrail` and `#BuildInPublic`. Confident-builder tone does not chase reach.

## Production checklist

Screenshots to capture from the live dashboard:
- [ ] Slide 1: full dashboard view with coach drawer expanded
- [ ] Slide 2: week detail page, ideally one with at least one active alert
- [ ] Slide 3: activity feed view, with a trail run that has a visible route polyline
- [ ] Slide 4: coach Q&A — pick a turn with a substantive, data-referenced answer

Slide 5 can be built in any tool (Figma, Canva, Keynote). Background should match the dashboard's monochromatic dark palette to keep visual consistency across the carousel.

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
