# Route Preview on Activity Cards

## Summary

Add a subtle SVG route trace as a background watermark on trail running and road running activity cards in the dashboard. The route shape is fetched from Garmin during sync, converted to an SVG path, and rendered at 8% opacity in the dashboard's copper color.

## Data Pipeline

### 1. Fetch GPS data during sync

During `sync_activities()`, after fetching the activity list via `get_activities_by_date()`, make an additional call for each running/trail activity:

```python
details = client.get_activity_details(activity_id, maxpoly=500)
```

`maxpoly=500` keeps the point count low — enough for a recognizable shape, small enough for inline SVG strings. Skip this call for strength_training and other non-GPS activities.

**Error handling:** Wrap each `get_activity_details()` call in try/except. On failure, log a warning and set `route_svg = None` for that activity. Add a 0.5s sleep between calls to avoid Garmin rate limiting. A failed details call must not break the overall sync.

**Sync impact:** Changes sync from 1 API call to N+1 (where N is the number of running activities, typically 2-4 per week). Adds ~2-4 seconds to sync time.

### 2. Extract polyline points

The details response contains GPS coordinates at `geoPolylineDTO.polyline`:

```python
poly_dto = details.get("geoPolylineDTO") or {}
raw_points = poly_dto.get("polyline", [])
points = [(p["lat"], p["lon"]) for p in raw_points if "lat" in p and "lon" in p]
```

If `geoPolylineDTO` is null or `polyline` is empty, set `route_svg = None`.

### 3. Convert polyline to SVG path

A new utility function `polyline_to_svg(points)` in `garmin_sync.py`:

- **Input:** List of `(lat, lon)` tuples
- **Early exit:** Return `None` if fewer than 2 distinct points.
- **Projection:** Simple equirectangular — multiply lon by `cos(radians(mid_lat))` for aspect correction. Mercator is unnecessary at trail scale (~20km).
- **Normalize:** Scale points to fit a `0 0 240 200` viewBox with 10px padding on all sides (effective drawing area: 220x180).
- **Simplify:** Apply Ramer-Douglas-Peucker with epsilon ~1.5 to reduce points to ~50-100, keeping the route recognizable while producing short SVG strings. Implement RDP inline (~30 lines of Python, no new dependency).
- **Output:** SVG path `d` attribute string using `M` (move) and `L` (line) commands. Typical output: 300-600 characters.
- **Validation:** Verify the output matches `^[ML0-9., -]+$` before returning. Return `None` if it doesn't match.

### 4. Store in cached JSON

Inject `route_svg` into the raw activity dict before caching to JSON:

```json
{
  "activityId": 22264525000,
  "activityName": "Cuajimalpa de Morelos Trail Running",
  "route_svg": "M60,180 L55,165 L45,155 L40,140 ...",
  ...
}
```

Activities without GPS data (strength, indoor) will have `route_svg: null`.

## Model Changes

Add to `GarminActivity` dataclass in `tracker/models.py`:

```python
route_svg: Optional[str] = None
```

Update `_normalize_activity()` in `garmin_sync.py` to read `route_svg` from the raw dict on cache load:

```python
route_svg=raw.get("route_svg"),
```

This ensures `route_svg` survives both the sync path (computed and injected) and the cache-load path (read from stored JSON).

## Server Changes

In `dashboard/serve.py`, add the `route` field to the activity serialization:

```python
entry = {
    ...existing fields...
    "route": a.route_svg,  # SVG path d-attribute or null
}
```

## Dashboard Changes

In `dashboard/dashboard.html`:

**CSS:** Add `position: relative; overflow: hidden;` to `.activity-card`. Both are required — `position: relative` scopes the SVG's absolute positioning to the card, `overflow: hidden` clips the SVG at card edges.

**JS:** Modify the activity card rendering. Wrap existing card content in a `<div>` with `position: relative; z-index: 1` so text stays above the SVG. Add the SVG before the content div:

```javascript
// Only for running activities with route data
let routeSvg = '';
if (isRun && a.route) {
  routeSvg = '<svg viewBox="0 0 240 200" preserveAspectRatio="xMidYMid meet"'
    + ' style="position:absolute;inset:10px;width:calc(100% - 20px);'
    + 'height:calc(100% - 20px);opacity:0.08;z-index:0;" fill="none"'
    + ' stroke="var(--copper)" stroke-width="2.5"'
    + ' stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="' + a.route + '"/></svg>';
}

html += '<div class="activity-card">' + routeSvg
  + '<div style="position:relative;z-index:1;">'
  + /* ...existing card content... */
  + '</div></div>';
```

## Cache Update

`weeks_cache.json` will include the `route` field after the next sync. For the static fallback, activities without route data simply won't show the watermark — graceful degradation, no visual breakage. Adds ~45-90KB to cache file across 30 weeks (modest).

## Scope Exclusions

- No map tiles or geographic context — route shape only
- No click-to-expand or interactive route viewing
- No elevation profile rendering
- No route data for non-running activities
- No retroactive fetching of old activities (only new syncs)

## Files to Modify

| File | Change |
|------|--------|
| `tracker/models.py` | Add `route_svg: Optional[str] = None` to `GarminActivity` |
| `tracker/garmin_sync.py` | Fetch activity details, add `polyline_to_svg()` + inline RDP, populate `route_svg`, add `route_svg` to `_normalize_activity()` |
| `dashboard/serve.py` | Pass `route` field in activity serialization |
| `dashboard/dashboard.html` | Add `position: relative; overflow: hidden` to card CSS, render SVG background with z-index layering on running cards |
| `dashboard/weeks_cache.json` | Updated on next sync (includes `route` field) |
