# Route Preview on Activity Cards

## Summary

Add a subtle SVG route trace as a background watermark on trail running and road running activity cards in the dashboard. The route shape is fetched from Garmin during sync, converted to an SVG path, and rendered at 8% opacity in the dashboard's copper color.

## Data Pipeline

### 1. Fetch GPS data during sync

During `sync.py`, after fetching the activity list via `get_activities_by_date()`, make an additional call for each running/trail activity:

```python
details = client.get_activity_details(activity_id, maxpoly=500)
```

`maxpoly=500` keeps the point count low — enough for a recognizable shape, small enough for inline SVG strings. Skip this call for strength_training and other non-GPS activities.

### 2. Extract polyline points

The details response contains GPS coordinate arrays. Extract the `(lat, lon)` pairs from the polyline data in the response.

### 3. Convert polyline to SVG path

A new utility function `polyline_to_svg(points)` in `garmin_sync.py`:

- **Input:** List of `(lat, lon)` tuples
- **Projection:** Simple equirectangular (multiply lon by `cos(mid_lat)` for aspect correction). Mercator is unnecessary at trail scale (~20km).
- **Normalize:** Scale points to fit a `0 0 240 200` viewBox with 10px padding on all sides (effective drawing area: 220x180).
- **Simplify:** Apply Ramer-Douglas-Peucker with epsilon ~1.5 to reduce points to ~50-100, keeping the route recognizable while producing short SVG strings.
- **Output:** SVG path `d` attribute string using `M` (move) and `L` (line) commands. Typical output: 300-600 characters.

### 4. Store in cached JSON

Add `route_svg` field to the activity object in the cached JSON file:

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

Update `_normalize_activity()` in `garmin_sync.py` to populate this field after fetching details.

## Server Changes

In `dashboard/serve.py`, add the `route` field to the activity serialization:

```python
entry = {
    ...existing fields...
    "route": a.route_svg,  # SVG path d-attribute or null
}
```

## Dashboard Changes

In `dashboard/dashboard.html`, modify the activity card rendering for trail/road running cards:

```javascript
// Only for running activities with route data
if ((isRun) && a.route) {
  html += '<svg viewBox="0 0 240 200" preserveAspectRatio="xMidYMid meet"'
    + ' style="position:absolute;inset:10px;width:calc(100% - 20px);'
    + 'height:calc(100% - 20px);opacity:0.08;" fill="none"'
    + ' stroke="var(--copper)" stroke-width="2.5"'
    + ' stroke-linecap="round" stroke-linejoin="round">'
    + '<path d="' + a.route + '"/></svg>';
}
```

The activity card CSS needs `position: relative` and `overflow: hidden` added (card already has `overflow` implicitly via border-radius).

## Cache Update

`weeks_cache.json` will include the `route` field after the next sync. For the static fallback, activities without route data simply won't show the watermark — graceful degradation, no visual breakage.

## Scope Exclusions

- No map tiles or geographic context — route shape only
- No click-to-expand or interactive route viewing
- No elevation profile rendering
- No route data for non-running activities
- No retroactive fetching of old activities (only new syncs)

## Files to Modify

| File | Change |
|------|--------|
| `tracker/models.py` | Add `route_svg: Optional[str]` to `GarminActivity` |
| `tracker/garmin_sync.py` | Fetch activity details, add `polyline_to_svg()`, populate `route_svg` |
| `dashboard/serve.py` | Pass `route` field in activity serialization |
| `dashboard/dashboard.html` | Render SVG background on running cards, add `position: relative` to card CSS |
| `dashboard/weeks_cache.json` | Updated on next sync (includes `route` field) |
