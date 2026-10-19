# Frontend Implementation Plan — AI Demand Planning & Decision Support System

> **For Cursor:** This document describes the complete frontend structure, screen-by-screen layout, component requirements, state management, and data contracts. The backend/model is already complete. Your job is to build the UI that connects to it. Follow this plan in order — each phase builds on the previous one.

---

## Tech Stack Assumptions

- **Framework:** React (or Next.js if routing is needed)
- **Styling:** Tailwind CSS
- **State:** Zustand or React Context (season-scoped global state)
- **Charts:** Recharts or Chart.js
- **Tables:** TanStack Table (react-table v8)
- **Icons:** Lucide React
- **Notifications/Alerts:** Sonner or React Hot Toast

If the stack differs, adapt accordingly — the component logic stays the same.

---

## Global Layout

### Persistent Shell

Every screen shares a top navigation bar and a left sidebar. Build these first.

**Top Nav Bar (always visible):**
- Product logo + name (left)
- Active season selector dropdown (center) — name, year, status badge
- Three live financial indicators (right): `Budget used: X%` · `Margin: X%` · `Coverage: X%`
- Each indicator is color-coded: green (on target) / amber (warning) / red (at risk)
- User avatar + settings (far right)

**Left Sidebar (collapsible):**

```
Season Setup          [icon: settings]
Dashboard             [icon: home]
─────────────────
Customer Coverage     [icon: users]
Product KPIs          [icon: bar-chart]
Budget Tracker        [icon: wallet]
─────────────────
Demand Projection     [icon: trending-up]
SKU Recommendations   [icon: package]
─────────────────
Order Validation      [icon: check-circle]
```

Active route is highlighted. Sidebar collapses to icon-only on narrow viewports.

**Global Scenario Switcher:**
A persistent pill toggle on all screens from Demand Projection onward:

```
[ Conservative ]  [ Base Case ✓ ]  [ Optimistic ]
```

Changing this re-renders all projected figures across the app without a page reload. Store selection in global state.

---

## Screen 1 — Season Setup & Data Import

**Route:** `/setup` or `/seasons/new`

**Purpose:** Configure a new season and import all source data before any AI analysis runs.

### Layout

Vertical stepper with 4 steps. Each step must be completed and validated before the next unlocks.

```
Step 1: Season Config
Step 2: Products
Step 3: Customers
Step 4: Supply Chain & Finance
```

Progress indicator at the top. "Complete Setup" button only activates when all 4 steps are valid.

### Step 1 — Season Config

Fields:
- Season name (text input, e.g. "AW 2025")
- Start date / End date (date pickers)
- Default currency (dropdown)
- Seasonal buying budget (number input with currency symbol)
- Target gross margin % (number input)

### Step 2 — Products

Two import methods (tabs):
1. **ERP Import** — trigger ERP sync, show progress + row count on success
2. **CSV Upload** — drag-and-drop zone, show column mapping UI after upload

After import, display a preview table with columns:
`SKU | Category | Season | Wholesale Price | Available Sizes | Status (new/carry-over/core) | Historical Units | Buying Customers`

Show row count and any validation errors (missing required fields highlighted in red).

### Step 3 — Customers

Same dual-import pattern (ERP sync / CSV upload).

Preview table columns:
`Customer ID | Typology | Region | Categories | Reorder Freq | Avg Basket | Status (visited/not-visited)`

Include a summary bar: `Total: 500 | Visited: 210 (42%) | Not visited: 290 (58%)`

Allow manual toggle of visited/not-visited status on any row.

### Step 4 — Supply Chain & Finance

Two sub-tabs:

**Supply Chain tab:**
Table of SKUs with editable columns:
`SKU | Physical Stock | Theoretical Stock | WIP Qty | Lead Time (days) | MOQ | Industrial Min per Size`

Support inline editing. Bulk-fill option for MOQ (apply same value to all rows).

**Finance tab:**
Table of SKUs with editable columns:
`SKU | Supplier Purchase Price | Currency | Transport & Duty Cost | Expected Margin %`

Plus season-level fields (already set in Step 1 but shown here for review):
- Seasonal buying budget
- Target gross margin %

### Completion

On "Complete Setup," validate all required fields and trigger the AI model's initialization call. Show a loading state ("Initializing demand model…") then redirect to Dashboard.

---

## Screen 2 — Season Dashboard

**Route:** `/dashboard`

**Purpose:** Command center for the active season. Surface KPIs, alerts, and entry points into analysis.

### Layout

**Alert strip (top, conditional):**
Dismissible banner strip. Shows one card per alert type:
- Budget overrun: "Purchase cost exceeds budget by X%"
- Margin miss: "X SKUs below target margin"
- Coverage risk: "Only X% of customers visited — projections have higher uncertainty"
- Stock-out risk: "X SKUs flagged for potential stock-out"

Each alert card has a "View" button that deep-links to the relevant screen.

**KPI cards row (6 cards):**

| Card | Value | Sub-label |
|------|-------|-----------|
| Commercial Coverage | 42% | 210 / 500 customers visited |
| Confirmed Orders | 12,450 units | Across 180 SKUs |
| Projected Demand | 18,200 units | Base case scenario |
| Budget Consumed | 68% | €340K of €500K |
| Gross Margin | 52.4% | Target: 50% |
| Reorder Rate | 34% | Avg across buying customers |

Each card is clickable and navigates to the relevant detail screen.

**Three entry-point cards (below KPIs):**

```
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│  Customer Coverage  │  │   Product KPIs      │  │   Budget Tracker    │
│  42% visited        │  │   180 active SKUs   │  │   €340K / €500K     │
│  [View Map →]       │  │   [Explore →]       │  │   [View Finance →]  │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
```

**Recent activity feed (bottom):**
Chronological list of decisions made: "SKU A1234 — quantity locked at 400 units by [user] — 2h ago"

---

## Screen 3a — Customer Coverage

**Route:** `/customers`

**Purpose:** Show which customers have been visited, which haven't, and how the AI is matching non-visited customers to similar profiles.

### Layout

Two-panel split: visualization (left, 60%) + customer table (right, 40%).

**Left panel — coverage visualization:**

Toggle between two views:
- **By Geography:** Map or treemap of customers colored by visited (teal) / not-visited (gray)
- **By Typology:** Stacked bar chart — for each typology (independent, chain, key account), show visited vs not-visited count

**Right panel — customer table:**

Columns: `Customer ID | Typology | Region | Visited | Matched To | Similarity Score`

Filters:
- Visited status (all / visited / not visited)
- Typology (multi-select)
- Region (multi-select)

**Cluster matching section (below or expandable from table row):**

For each non-visited customer, show which visited customer cluster they've been matched to and the top 3 behavioral similarities used (e.g. "Same typology, overlapping categories, similar basket size"). Confidence score shown as a colored badge (high / medium / low).

Clicking a customer row opens a slide-over with full purchase history and the AI's projection for that customer.

---

## Screen 3b — Product KPI Explorer

**Route:** `/products`

**Purpose:** Browse and analyze KPIs across all SKUs.

### Layout

**Filter bar (top):**
- Search by SKU or name
- Category (multi-select)
- Product status: new / carry-over / core (multi-select)
- Season (dropdown)
- Sort by: diffusion rate / reorder rate / units sold / depth per customer

**Main table:**

Columns:

| Column | Description |
|--------|-------------|
| SKU | Identifier + category badge |
| Status | new / carry-over / core pill |
| Diffusion Rate | Buying customers / total active customers — shown as % + progress bar |
| Depth / Customer | Avg units per buying customer |
| Reorder Rate | % of buying customers who reordered |
| Total Units Sold | Historical |
| Buying Customers | Count |
| Size Breakdown | Sparkline bar showing size distribution |
| AI Confidence | High / Medium / Low badge |

Row click opens the SKU detail slide-over (same component used in the Recommendation screen).

**SKU detail slide-over:**

Contains:
- Full historical size breakdown (bar chart)
- Season-over-season trend (line chart)
- KPIs panel: all 6 mandatory KPIs with their values
- "View Recommendation →" button that navigates to that SKU in Screen 5

---

## Screen 3c — Budget Tracker

**Route:** `/budget`

**Purpose:** Real-time financial overview of the season's purchase commitments vs targets.

### Layout

**Summary row (top, 4 cards):**

| Card | Value |
|------|-------|
| Total Purchase Cost | €340,000 |
| Seasonal Budget | €500,000 |
| Expected Turnover | €720,000 |
| Gross Margin | 52.4% |

**Budget consumption bar:**

A horizontal progress bar showing purchase cost vs budget. Threshold markers at 80% (warning) and 100% (danger). Current scenario label shown above.

Scenario toggle here rerenders the bar for conservative / base / optimistic projections.

**Per-category breakdown table:**

| Category | Purchase Cost | % of Budget | Margin % | Status |
|----------|---------------|-------------|----------|--------|
| Leather | €120,000 | 24% | 54% | ✓ On target |
| Textile | €95,000 | 19% | 49% | ⚠ Below margin |
| Parka | €125,000 | 25% | 55% | ✓ On target |

Row expand shows per-SKU breakdown within that category.

**Margin alert list:**
SKUs where projected margin falls below target are listed with their current margin, target margin, and a "Fix" button that links directly to that SKU's recommendation panel.

---

## Screen 4 — Demand Projection Engine

**Route:** `/projection`

**Purpose:** Show how the AI has split projected demand across confirmed orders, probable reorders, and non-visited customer demand. This is the transparency screen for the model's outputs.

### Layout

**Scenario switcher (persistent, top):**
Conservative / Base Case / Optimistic. Changes all numbers on this screen.

**Total demand summary (top):**

```
Total Projected Units: 18,200
├── Confirmed orders:        12,450  (68%)
├── Probable reorders:        3,200  (18%)
└── Non-visited projection:   2,550  (14%)
```

Stacked bar chart for visual breakdown. Tooltip shows absolute numbers.

**Per-SKU projection table:**

Columns: `SKU | Confirmed | Probable Reorders | Projected | Total | Confidence | Explainability`

The "Explainability" column has a `Why?` button that expands an inline explanation:

```
Why 420 units?
─────────────────────────────────────────────
Confirmed orders:     280 units (confirmed by 34 customers)
Probable reorders:     90 units (based on 31% reorder rate, 9 customers likely)
Non-visited demand:    50 units (12 non-visited customers matched to similar profiles)

Key signals used:
• Diffusion rate: 12% (broad spread — high reorder confidence)
• Depth per customer: 8.2 units (consistent ordering pattern)
• Customer cluster: 12 non-visited matched to "Independent, Mid-basket" profile
• Scenario: Base case (1.0× multiplier applied)
```

This explainability panel must appear on every SKU row. It is non-negotiable per the spec.

**Projection confidence distribution (sidebar or bottom):**
Pie or donut chart showing count of SKUs by confidence level (High / Medium / Low). Low-confidence SKUs are flagged for human review.

---

## Screen 5 — SKU Recommendation View

**Route:** `/recommendations`

**Purpose:** The primary working screen. Users review, adjust, and lock AI recommendations per SKU.

### Layout

**Left panel — SKU list (30% width):**

Filterable and sortable list. Each row shows:
- SKU + category
- Recommended total qty
- Confidence badge
- Lock icon (locked = frozen from further AI recalculation)
- Status indicator: pending / adjusted / locked / validated

Filter bar: by category, status, confidence level, margin status.

**Right panel — SKU detail (70% width):**

Sections top to bottom:

**1. Header:**
`SKU: A1234 — Leather Jacket — Core | Season: AW 2025`
Lock toggle button (top right). When locked, all editable fields become read-only.

**2. Demand breakdown:**
Horizontal stacked bar: confirmed / probable / projected (same as Screen 4, SKU-level).
`Total recommended: 420 units`

**3. Quantity adjustment:**
Number input for total recommended quantity. Changing this triggers:
- Automatic size curve recalculation
- Live financial impact update (purchase cost, margin)
- A yellow "modified" badge appears

"Reset to AI recommendation" link appears when modified.

**4. Size breakdown chart + editor:**

Bar chart showing recommended units per size (e.g. XS / S / M / L / XL).
Below the chart, an editable table:

| Size | Recommended | Manual Override | Final Qty |
|------|-------------|-----------------|-----------|
| XS | 20 | — | 20 |
| S | 80 | 100 | 100 |
| M | 160 | — | 160 |
| L | 120 | — | 120 |
| XL | 40 | — | 40 |

Modified cells highlighted in amber. "Apply optimal size curve" button resets to AI recommendation.

**5. Explainability panel (always visible, collapsible):**

Same format as Screen 4 — shows KPIs, assumptions, and demand split used to generate the recommendation. `Why this quantity?` as the panel heading.

**6. Financial impact card:**

```
Purchase cost:      €3,360   (420 × €8.00)
Expected turnover:  €7,140   (420 × €17.00)
Gross margin:       €3,780   (53%)
Budget impact:      +0.67% of season budget
```

Color-coded: green if margin ≥ target, red if below. Updates live when quantity or size is adjusted.

**7. Action buttons:**
- `Save changes` — saves adjustments without locking
- `Lock SKU` — freezes this SKU, excludes it from further AI recalculation
- `Mark for review` — flags it for another team member

---

## Screen 6a — Size Distribution Editor

**Route:** Accessible as a modal or slide-over from Screen 5, not a standalone route.

**Purpose:** Fine-grained size curve editing with business rules.

### Layout

**Top: Curve comparison chart**
Dual bar chart — AI recommended size curve (blue) vs historical actual sales (gray). Distortions caused by past stock-outs shown with a warning icon and annotation.

**Middle: Rule configuration panel**

Per-size rules table:

| Size | Min Units | Max Units | Blocked | Rounding |
|------|-----------|-----------|---------|----------|
| XS | 10 | 50 | ☐ | — |
| S | 20 | — | ☐ | — |
| M | 30 | — | ☐ | — |
| L | 20 | — | ☐ | MOQ ×6 |
| XL | 10 | 40 | ☑ | — |

Blocked sizes are excluded from the recommendation. Rounding applies MOQ-compatible rounding.

**Bottom: Live preview**
As rules are changed, the recommended size curve updates in real time, along with total units and purchase cost.

`Apply rules` button pushes changes back to the SKU detail panel.

---

## Screen 6b — Financial Validation (per-SKU panel)

**Route:** Slide-over from Screen 5, triggered by the financial impact card.

Already described inline in Screen 5's financial impact card. If a full-screen view is needed:

Show all locked + pending SKUs in a table with their financial metrics, budget contribution, and margin status. A running total at the bottom. Budget overrun highlighted in red.

---

## Screen 7 — Order Validation & Export

**Route:** `/validation`

**Purpose:** Final human sign-off before any order is committed or exported to ERP.

### Layout

**Scenario comparison table (top):**

Side-by-side columns for Conservative / Base / Optimistic:

| Metric | Conservative | Base Case | Optimistic |
|--------|-------------|-----------|------------|
| Total units | 15,800 | 18,200 | 21,400 |
| Purchase cost | €290K | €340K | €400K |
| Budget usage | 58% | 68% | 80% |
| Gross margin | 54% | 52% | 50% |
| SKUs at risk | 3 | 5 | 8 |

Active scenario highlighted. User can switch active scenario here (last chance before export).

**Override summary table:**

Lists every SKU where the user manually adjusted the AI recommendation:

| SKU | AI Recommended | User Override | Reason Tag | Notes |
|-----|---------------|---------------|------------|-------|
| A1234 | 420 units | 380 units | Risk reduction | — |
| B5678 | 200 units | 250 units | Commercial commitment | Key account request |

**Decision audit trail (expandable):**
Full log of every change made during the session: who made it, when, what changed. This feeds the traceability requirement.

**Validation action (bottom, prominent):**

This must feel deliberate — not a casual click.

```
┌─────────────────────────────────────────────────────┐
│  You are about to validate the AW 2025 season order │
│  18,200 units across 180 SKUs · Budget: €340,000    │
│                                                      │
│  [ Cancel ]              [ Confirm & Export to ERP ] │
└─────────────────────────────────────────────────────┘
```

Clicking "Confirm & Export" triggers:
1. Write decision log to backend (full audit record)
2. ERP export API call
3. Season status updates to "Validated"
4. Redirect to a confirmation screen with export summary

**Post-validation:** Show a read-only summary of the validated order. Allow download as PDF/CSV. Season enters read-only mode — no further edits allowed unless explicitly reopened.

---

## Shared Components Checklist

Build these as reusable components that appear across multiple screens:

| Component | Used On |
|-----------|---------|
| `<KPICard>` | Dashboard, Budget Tracker |
| `<AlertBanner>` | Dashboard, Financial Validation |
| `<ScenarioSwitcher>` | Global (screens 4, 5, 7) |
| `<ExplainabilityPanel>` | Projection, Recommendation |
| `<DemandSplitBar>` | Projection, Recommendation |
| `<SizeBreakdownChart>` | Product KPIs, Recommendation, Size Editor |
| `<FinancialImpactCard>` | Recommendation, Validation |
| `<SKUTable>` | Product KPIs, Recommendation list |
| `<CustomerTable>` | Customer Coverage |
| `<ImportZone>` | Setup (products + customers) |
| `<ConfidenceBadge>` | Projection, Recommendation |
| `<LockToggle>` | Recommendation |
| `<AuditTrail>` | Validation |

---

## State Management

Use a global store (Zustand recommended) with these slices:

```
seasonStore
  ├── activeSeason (id, name, status, budget, targetMargin)
  ├── activeScenario ('conservative' | 'base' | 'optimistic')
  └── financialSummary (budgetUsed, margin, coverage) → drives top nav indicators

productsStore
  ├── skus[] (all SKU data)
  ├── overrides{} (skuId → { qty, sizes, locked, notes })
  └── recommendations{} (skuId → AI recommendation object)

customersStore
  ├── customers[]
  ├── clusters[] (cluster assignments from model)
  └── coverageStats

uiStore
  ├── activeSKU (for recommendation panel)
  └── alerts[]
```

The `activeScenario` field is the most important — every computed projection value should be derived from it. When scenario changes, recalculate displayed values without re-fetching from the API (the model should return all three scenarios in one response if possible).

---

## API Contract Assumptions

The model is already built. The frontend will call these endpoints (adjust names to match actual implementation):

| Endpoint | Used By |
|----------|---------|
| `POST /seasons` | Setup — create season |
| `POST /seasons/:id/import` | Setup — trigger ERP/CSV import |
| `GET /seasons/:id/dashboard` | Dashboard KPIs + alerts |
| `GET /seasons/:id/customers` | Customer Coverage |
| `GET /seasons/:id/products` | Product KPI Explorer |
| `GET /seasons/:id/projection` | Demand Projection (returns all 3 scenarios) |
| `GET /seasons/:id/recommendations` | SKU Recommendations (all 3 scenarios) |
| `PUT /seasons/:id/recommendations/:skuId` | Save manual override |
| `POST /seasons/:id/validate` | Final sign-off + ERP export trigger |

All endpoints that return projected figures should include all three scenario variants so the global scenario switcher works client-side without extra API calls.

---

## Implementation Order

Build in this sequence to minimize blocked dependencies:

1. **Global shell** — nav bar, sidebar, routing, scenario switcher state
2. **Screen 1** — Season Setup (no model dependency, pure forms)
3. **Screen 2** — Dashboard (read-only, good for API integration testing)
4. **Shared components** — KPICard, AlertBanner, ConfidenceBadge, ExplainabilityPanel
5. **Screen 4** — Demand Projection (read-only, model output display)
6. **Screen 5** — SKU Recommendations (most complex, build last among analysis screens)
7. **Screen 3a, 3b, 3c** — Customer, Products, Budget (parallel, no dependencies on each other)
8. **Screen 6a** — Size Editor (modal, depends on Screen 5)
9. **Screen 7** — Validation & Export (depends on all recommendation state being stable)

---

## Non-Negotiable UX Rules (from spec)

These are hard requirements, not suggestions:

- Every AI recommendation must have a visible `Why?` button showing the ExplainabilityPanel. No exceptions.
- No order can be committed without explicit human validation (Screen 7 confirm action).
- Users must be able to override any quantity or size split at any point before validation.
- Locked SKUs must be visually distinct and not silently re-calculated by the model.
- All changes are logged with timestamp and user identity.
- No black-box outputs — if a KPI or assumption is used, it must be visible on screen.
- Business rules (MOQ, size minimums, blocked sizes) must be configurable from the UI without a code change.
