# Monthly Summary + Over-Plan Alert Logic

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Month at a Glance" summary section between the progress bar and week selector, and apply consistent over-plan alert styling (red warnings when actual exceeds planned by >10%) across the entire dashboard.

**Architecture:** All changes in `dashboard.html` (single-file app). New CSS classes for alert states + over-plan bar colors. New `renderMonthlySummary()` JS function computes calendar-month aggregates from `WEEKS` data. Existing `deltaClass()` function updated to return an alert class for over-plan metrics. The monthly summary is static per data load (not per-week-selection), rendered once in initial load.

**Tech Stack:** HTML, CSS, JS (vanilla), existing design system tokens

---

### Task 1: Add over-plan alert CSS classes

**Files:**
- Modify: `dashboard/dashboard.html:373-417` (CSS delta/bar section)

- [ ] **Step 1: Add `--over` delta class after line 375**

After `.metric-card__delta--neutral`:
```css
.metric-card__delta--over { background: rgba(160, 64, 48, 0.18); color: #e06050; }
```

- [ ] **Step 2: Add `--over` bar fill class after line 417**

After `.metric-card__bar-fill--gym`:
```css
.metric-card__bar-fill--over { background: linear-gradient(90deg, var(--canyon-red), #c94040); }
```

- [ ] **Step 3: Add alert-state metric card class**

After the bar fill classes:
```css
.metric-card--alert { border-color: rgba(160, 64, 48, 0.3); background: rgba(160, 64, 48, 0.06); }
.metric-card--alert .metric-card__label { color: #e06050; }
```

- [ ] **Step 4: Add `--danger` alert card icon class after line 575**

After `.alert-card__icon--warning`:
```css
.alert-card__icon--danger { background: rgba(160, 64, 48, 0.15); color: #e06050; }
```

---

### Task 2: Update deltaClass() to detect over-plan

**Files:**
- Modify: `dashboard/dashboard.html:1046-1051` (deltaClass function)

- [ ] **Step 1: Update deltaClass to return `--over` when delta > 10%**

Replace the function:
```javascript
function deltaClass(d) {
  if (d == null) return '';
  if (d > 10) return 'metric-card__delta--over';
  if (d > 1) return 'metric-card__delta--positive';
  if (d < -1) return 'metric-card__delta--negative';
  return 'metric-card__delta--neutral';
}
```

---

### Task 3: Update renderStats() for over-plan bar colors and card alerts

**Files:**
- Modify: `dashboard/dashboard.html:1152-1192` (metric card rendering in renderStats)

- [ ] **Step 1: Add over-plan detection and card/bar class logic**

Replace the `metricsHtml` forEach block (lines 1152-1192) with logic that:
- Detects if delta > 10% (over-plan alert)
- Adds `metric-card--alert` class to the card wrapper
- Swaps bar fill class to `metric-card__bar-fill--over` when over-plan
- Prepends warning icon `⚠` to the label text when over-plan

```javascript
let metricsHtml = '';
metrics.forEach(m => {
  const planned = w.plan[m.key];
  const actual = hasActual ? w.actual[m.key] : null;
  const isGym = m.key === 'gym';
  const d = isGym ? (actual != null ? actual - planned : null) : delta(actual, planned);
  const dStr = isGym ? formatDelta(d, true) : formatDelta(d, false);
  const dClass = deltaClass(d);
  const pct = actual != null ? Math.min((actual / planned) * 100, 100) : 0;
  const isOver = d != null && d > 10;
  const cardAlert = isOver ? ' metric-card--alert' : '';
  const barClass = isOver ? 'over' : m.barClass;
  const labelPrefix = isOver ? '&#9888; ' : '';

  let valuesHtml;
  if (hasActual) {
    valuesHtml = '<div class="metric-card__dual">'
      + '<div class="metric-card__value-group">'
      + '<span class="metric-card__value-tag metric-card__value-tag--actual">Actual</span>'
      + '<span class="metric-card__value-num metric-card__value-num--actual">' + actual + ' <span class="metric-card__value-unit">' + m.unit + '</span></span>'
      + '</div>'
      + '<div class="metric-card__value-group">'
      + '<span class="metric-card__value-tag metric-card__value-tag--planned">Planned</span>'
      + '<span class="metric-card__value-num metric-card__value-num--planned">' + planned + ' <span class="metric-card__value-unit">' + m.unit + '</span></span>'
      + '</div></div>';
  } else {
    valuesHtml = '<div class="metric-card__dual">'
      + '<div class="metric-card__value-group">'
      + '<span class="metric-card__value-tag metric-card__value-tag--planned">Target</span>'
      + '<span class="metric-card__value-num metric-card__value-num--solo">' + planned + ' <span class="metric-card__value-unit">' + m.unit + '</span></span>'
      + '</div></div>'
      + '<div class="metric-card__empty-note">Awaiting sync...</div>';
  }

  metricsHtml += '<div class="metric-card' + cardAlert + '">'
    + '<div class="metric-card__header">'
    + '<div class="metric-card__icon metric-card__icon--' + m.iconClass + '">' + m.icon + '</div>'
    + (dStr ? '<span class="metric-card__delta ' + dClass + '">' + dStr + '</span>' : '')
    + '</div>'
    + '<div class="metric-card__label">' + labelPrefix + m.label + '</div>'
    + valuesHtml
    + '<div class="metric-card__bar">'
    + '<div class="metric-card__bar-fill metric-card__bar-fill--' + barClass + '" data-width="' + pct + '"></div>'
    + '</div></div>';
});
```

---

### Task 4: Update chart bars for over-plan weeks

**Files:**
- Modify: `dashboard/dashboard.html:531-534` (chart bar CSS)
- Modify: `dashboard/dashboard.html:1417-1421` (chart bar rendering)

- [ ] **Step 1: Add CSS class for over-plan chart bar**

After `.chart-bar--actual`:
```css
.chart-bar--over {
  background: linear-gradient(180deg, #e06050, var(--canyon-red));
  box-shadow: 0 0 12px rgba(160, 64, 48, 0.25);
}
```

- [ ] **Step 2: Update chart rendering to use over-plan bar color**

Replace the actual bar rendering block (lines 1417-1421):
```javascript
if (w.actual) {
  const actualH = (w.actual.distance_km / maxDist * 100).toFixed(0);
  const overPlan = w.actual.distance_km > w.plan.distance_km * 1.1;
  const barType = overPlan ? 'chart-bar--over' : 'chart-bar--actual';
  barsHtml += '<div class="chart-bar ' + barType + '" data-height="' + actualH + '" style="height:0">'
    + '<span class="chart-bar-value">' + w.actual.distance_km + '</span></div>';
}
```

---

### Task 5: Add monthly summary HTML placeholder

**Files:**
- Modify: `dashboard/dashboard.html:956-958` (between progress bar label and week selector)

- [ ] **Step 1: Insert monthly summary div between progress bar and week selector**

After the `</header>` closing tag (line 956), before the week selector comment:
```html
<!-- ═══════════ MONTHLY SUMMARY ═══════════ -->
<div class="month-summary" id="monthSummary"></div>
```

---

### Task 6: Add monthly summary CSS

**Files:**
- Modify: `dashboard/dashboard.html` (CSS section, after progress bar styles ~line 141)

- [ ] **Step 1: Add all monthly summary CSS classes**

Insert after `.progress-bar__label` styles (line 141):

```css
/* ── Monthly Summary ── */
.month-summary {
  background: linear-gradient(135deg, var(--bg-card), var(--bg-card-alt));
  border: 1px solid var(--border); border-radius: var(--radius);
  padding: 24px 28px 22px; margin-bottom: 28px;
  opacity: 0; animation: fadeUp 0.6s ease 0.4s forwards;
}
.month-summary__header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 20px; padding-bottom: 14px; border-bottom: 1px solid var(--border);
}
.month-summary__title {
  font-family: 'Syne', sans-serif; font-weight: 700; font-size: 1.1rem;
  color: var(--text-primary); display: flex; align-items: center; gap: 10px;
}
.month-summary__title-icon { font-size: 0.85rem; opacity: 0.7; }
.month-summary__badge {
  font-family: 'JetBrains Mono', monospace; font-size: 0.58rem; font-weight: 600;
  letter-spacing: 0.12em; text-transform: uppercase; padding: 4px 10px; border-radius: 20px;
}
.month-summary__badge--ok {
  background: rgba(61, 139, 94, 0.12); color: var(--forest-light);
  border: 1px solid rgba(61, 139, 94, 0.2);
}
.month-summary__badge--warn {
  background: rgba(160, 64, 48, 0.15); color: #e06050;
  border: 1px solid rgba(160, 64, 48, 0.3);
}
.month-summary__grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
}
.month-stat {
  padding: 14px 16px; background: rgba(0, 0, 0, 0.2);
  border-radius: var(--radius-sm); border: 1px solid rgba(28, 34, 48, 0.6);
  transition: border-color 0.3s ease;
}
.month-stat:hover { border-color: var(--border-accent); }
.month-stat--alert {
  border-color: rgba(160, 64, 48, 0.3); background: rgba(160, 64, 48, 0.06);
}
.month-stat--alert:hover { border-color: rgba(160, 64, 48, 0.45); }
.month-stat--alert .month-stat__label { color: #e06050; }
.month-stat__label {
  font-family: 'JetBrains Mono', monospace; font-size: 0.52rem; font-weight: 500;
  letter-spacing: 0.16em; text-transform: uppercase; color: var(--text-tertiary); margin-bottom: 8px;
}
.month-stat__value {
  font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.45rem;
  line-height: 1; color: var(--text-primary); margin-bottom: 4px;
}
.month-stat__value span {
  font-size: 0.7rem; font-weight: 500; color: var(--text-secondary);
  font-family: 'Outfit', sans-serif; margin-left: 2px;
}
.month-stat__sub {
  font-family: 'JetBrains Mono', monospace; font-size: 0.52rem;
  color: var(--text-secondary); margin-bottom: 8px;
}
.month-stat__bar {
  width: 100%; height: 4px; background: rgba(28, 34, 48, 0.8);
  border-radius: 2px; overflow: hidden; margin-top: 10px;
}
.month-stat__bar-fill {
  height: 100%; border-radius: 2px; width: 0; transition: width 1s ease;
}
.month-stat__bar-fill--on-track { background: linear-gradient(90deg, var(--forest), var(--forest-light)); }
.month-stat__bar-fill--over { background: linear-gradient(90deg, var(--canyon-red), #c94040); }
.month-stat__bar-fill--copper { background: linear-gradient(90deg, var(--copper), var(--copper-light)); }
.month-stat__delta {
  font-family: 'JetBrains Mono', monospace; font-size: 0.5rem; font-weight: 600;
  padding: 2px 6px; border-radius: 3px; display: inline-block; margin-top: 6px;
}
.month-stat__delta--up { background: rgba(61, 139, 94, 0.12); color: var(--forest-light); }
.month-stat__delta--over { background: rgba(160, 64, 48, 0.18); color: #e06050; }
.month-stat--pace { grid-column: span 2; }
.month-stat--pace .month-stat__paces { display: flex; gap: 16px; margin-top: 4px; }
.pace-item { flex: 1; }
.pace-item__type {
  font-family: 'JetBrains Mono', monospace; font-size: 0.48rem; font-weight: 500;
  letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-tertiary);
  margin-bottom: 5px; display: flex; align-items: center; gap: 5px;
}
.pace-item__dot { width: 5px; height: 5px; border-radius: 50%; display: inline-block; }
.pace-item__dot--trail { background: var(--copper); }
.pace-item__dot--road { background: var(--forest); }
.pace-item__value {
  font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.15rem;
  line-height: 1; color: var(--text-primary);
}
.pace-item__value span {
  font-size: 0.6rem; font-weight: 500; color: var(--text-secondary);
  font-family: 'Outfit', sans-serif; margin-left: 1px;
}
.pace-item__sub {
  font-family: 'JetBrains Mono', monospace; font-size: 0.48rem;
  color: var(--text-tertiary); margin-top: 3px;
}
.pace-divider { width: 1px; background: var(--border); align-self: stretch; margin: 2px 0; }

@media (max-width: 768px) {
  .month-summary { padding: 18px 16px 16px; }
  .month-summary__grid { grid-template-columns: repeat(2, 1fr); }
  .month-stat--pace { grid-column: 1 / -1; }
}
```

---

### Task 7: Add renderMonthlySummary() function

**Files:**
- Modify: `dashboard/dashboard.html` (JS section, before renderAll ~line 1486)

- [ ] **Step 1: Add the renderMonthlySummary function**

Insert before `renderAll()`:

```javascript
// ═══════════════════════════════════════════════════════
// RENDER: Monthly Summary
// ═══════════════════════════════════════════════════════
function renderMonthlySummary() {
  const container = document.getElementById('monthSummary');
  if (!container) return;

  // Determine current month from the selected week's data
  const sw = WEEKS[selectedWeek];
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const selMonth = sw.start.split(' ')[0]; // e.g. "Mar"
  const selYear = sw.year;
  const monthIdx = months.indexOf(selMonth);
  const monthName = ['January','February','March','April','May','June','July','August','September','October','November','December'][monthIdx];

  // Filter weeks that overlap with this calendar month
  const monthWeeks = WEEKS.filter(w => {
    const startMonth = w.start.split(' ')[0];
    const endMonth = w.end.split(' ')[0];
    return (startMonth === selMonth || endMonth === selMonth) && w.year === selYear;
  });

  // Aggregate planned & actual
  let planDist = 0, planVert = 0, actDist = 0, actVert = 0;
  let totalDur = 0, totalActivities = 0, compSum = 0, compCount = 0;
  let trailPaces = [], roadPaces = [], trailDist = 0, roadDist = 0, trailRuns = 0, roadRuns = 0;

  monthWeeks.forEach(w => {
    planDist += w.plan.distance_km;
    planVert += w.plan.vert_m;

    if (w.actual) {
      actDist += w.actual.distance_km;
      actVert += w.actual.vert_m;
    }
    if (w.compliance != null) {
      compSum += w.compliance;
      compCount++;
    }
    if (w.activities) {
      w.activities.forEach(a => {
        totalActivities++;
        if (a.dur) totalDur += a.dur;
        if (a.pace && a.dist) {
          const parts = a.pace.split(':');
          const paceSec = parseInt(parts[0]) * 60 + parseInt(parts[1]);
          if (a.type === 'trail') {
            trailPaces.push({ sec: paceSec, dist: a.dist });
            trailDist += a.dist;
            trailRuns++;
          } else if (a.type === 'running' || a.type === 'road') {
            roadPaces.push({ sec: paceSec, dist: a.dist });
            roadDist += a.dist;
            roadRuns++;
          }
        }
      });
    }
  });

  // No data at all? Hide
  if (compCount === 0 && actDist === 0) {
    container.innerHTML = '';
    return;
  }

  // Weighted average paces
  function avgPace(paces, totalD) {
    if (paces.length === 0 || totalD === 0) return null;
    const weightedSec = paces.reduce((sum, p) => sum + p.sec * p.dist, 0) / totalD;
    const m = Math.floor(weightedSec / 60);
    const s = Math.round(weightedSec % 60);
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  const trailPace = avgPace(trailPaces, trailDist);
  const roadPace = avgPace(roadPaces, roadDist);
  const avgComp = compCount > 0 ? Math.round(compSum / compCount) : null;
  const totalHrs = (totalDur / 60).toFixed(1);

  // Deltas
  const distDelta = planDist > 0 ? ((actDist - planDist) / planDist * 100) : 0;
  const vertDelta = planVert > 0 ? ((actVert - planVert) / planVert * 100) : 0;
  const distOver = distDelta > 10;
  const vertOver = vertDelta > 10;
  const alertCount = (distOver ? 1 : 0) + (vertOver ? 1 : 0);

  // Badge
  const badgeClass = alertCount > 0 ? 'month-summary__badge--warn' : 'month-summary__badge--ok';
  const badgeText = alertCount > 0
    ? '&#9888; ' + alertCount + ' Alert' + (alertCount > 1 ? 's' : '')
    : '&#10003; On Track';

  // Stat helpers
  function statBar(pct, isOver) {
    const cls = isOver ? 'month-stat__bar-fill--over' : 'month-stat__bar-fill--on-track';
    const w = Math.min(pct, 100);
    return '<div class="month-stat__bar"><div class="month-stat__bar-fill ' + cls + '" data-mwidth="' + w + '"></div></div>';
  }
  function statDelta(val, isOver) {
    if (isOver) return '<span class="month-stat__delta month-stat__delta--over">&#9888; +' + val.toFixed(1) + '% over plan</span>';
    return '<span class="month-stat__delta month-stat__delta--up">+' + val.toFixed(1) + '%</span>';
  }

  let html = '<div class="month-summary__header">'
    + '<div class="month-summary__title"><span class="month-summary__title-icon">&#9670;</span>' + monthName + ' ' + selYear + '</div>'
    + '<span class="month-summary__badge ' + badgeClass + '">' + badgeText + '</span>'
    + '</div><div class="month-summary__grid">';

  // Distance
  const distPct = planDist > 0 ? (actDist / planDist * 100) : 0;
  html += '<div class="month-stat' + (distOver ? ' month-stat--alert' : '') + '">'
    + '<div class="month-stat__label">' + (distOver ? '&#9888; ' : '') + 'Distance</div>'
    + '<div class="month-stat__value">' + actDist.toFixed(1) + ' <span>km</span></div>'
    + '<div class="month-stat__sub">of ' + planDist + ' km planned</div>'
    + statBar(distPct, distOver)
    + (distDelta >= 0 ? statDelta(distDelta, distOver) : '')
    + '</div>';

  // Elevation
  const vertPct = planVert > 0 ? (actVert / planVert * 100) : 0;
  html += '<div class="month-stat' + (vertOver ? ' month-stat--alert' : '') + '">'
    + '<div class="month-stat__label">' + (vertOver ? '&#9888; ' : '') + 'Elevation</div>'
    + '<div class="month-stat__value">' + actVert.toLocaleString() + ' <span>m</span></div>'
    + '<div class="month-stat__sub">of ' + planVert.toLocaleString() + ' m planned</div>'
    + statBar(vertPct, vertOver)
    + (vertDelta >= 0 ? statDelta(vertDelta, vertOver) : '')
    + '</div>';

  // Avg Compliance
  html += '<div class="month-stat">'
    + '<div class="month-stat__label">Avg Compliance</div>'
    + '<div class="month-stat__value">' + (avgComp != null ? avgComp : '—') + ' <span>%</span></div>'
    + '<div class="month-stat__sub">across ' + compCount + ' week' + (compCount !== 1 ? 's' : '') + '</div>'
    + statBar(avgComp || 0, false)
    + (avgComp != null ? '<span class="month-stat__delta month-stat__delta--up">' + (avgComp >= 90 ? 'Excellent' : avgComp >= 70 ? 'Good' : 'Needs work') + '</span>' : '')
    + '</div>';

  // Training Hours
  html += '<div class="month-stat">'
    + '<div class="month-stat__label">Training Hours</div>'
    + '<div class="month-stat__value">' + totalHrs + ' <span>hrs</span></div>'
    + '<div class="month-stat__sub">' + totalActivities + ' sessions this month</div>'
    + '</div>';

  // Pace Breakdown
  html += '<div class="month-stat month-stat--pace">'
    + '<div class="month-stat__label">Avg Pace Breakdown</div>'
    + '<div class="month-stat__paces">'
    + '<div class="pace-item">'
    + '<div class="pace-item__type"><span class="pace-item__dot pace-item__dot--trail"></span>Trail</div>'
    + '<div class="pace-item__value">' + (trailPace || '—') + ' <span>/km</span></div>'
    + '<div class="pace-item__sub">' + trailRuns + ' run' + (trailRuns !== 1 ? 's' : '') + ' &middot; ' + trailDist.toFixed(1) + ' km</div>'
    + '</div>'
    + '<div class="pace-divider"></div>'
    + '<div class="pace-item">'
    + '<div class="pace-item__type"><span class="pace-item__dot pace-item__dot--road"></span>Road</div>'
    + '<div class="pace-item__value">' + (roadPace || '—') + ' <span>/km</span></div>'
    + '<div class="pace-item__sub">' + roadRuns + ' run' + (roadRuns !== 1 ? 's' : '') + ' &middot; ' + roadDist.toFixed(1) + ' km</div>'
    + '</div></div></div>';

  html += '</div>';
  container.innerHTML = html;

  // Animate bars
  requestAnimationFrame(() => {
    setTimeout(() => {
      container.querySelectorAll('.month-stat__bar-fill').forEach(bar => {
        bar.style.width = bar.dataset.mwidth + '%';
      });
    }, 50);
  });
}
```

- [ ] **Step 2: Add renderMonthlySummary() to renderAll()**

Update `renderAll()` to call it:
```javascript
function renderAll() {
  renderMonthlySummary();
  renderSelector();
  renderStats();
  renderActionBar();
  renderActivities();
  renderChart();
  renderAlerts();
}
```

---

### Task 8: Commit

- [ ] **Step 1: Commit all changes**

```bash
git add dashboard/dashboard.html
git commit -m "feat: add monthly summary section + over-plan alert styling"
```
