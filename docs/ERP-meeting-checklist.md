# Joolan ERP Integration — Meeting Checklist

**Goal:** get the Forecaster pulling live data from Joolan.
**Lead with this:** *"If you enable `query.do` (read-only) and send us the schema for the sales, cost, and customer tables, that covers almost everything in one shot."*

---

## 1. Priority — `query.do` + database schema

- [ ] Enable **`api_query`** (read-only SQL) on our API key
- [ ] Send **table + column names** for:
  - [ ] B2B / négoce sales — order **headers + lines** (our main forecasting input)
  - [ ] Retail ticket sales — headers + lines + règlements
  - [ ] Products / SKUs, clients, suppliers, receptions

*Why:* `query.do` runs plain `SELECT` statements. One endpoint covers history, cost, and customers — but only if we know the table names. **The schema is the real blocker, not the permission.**

## 2. Confirm the data inside those tables

- [ ] **Sales history:** B2B (négoce) orders included? Each sale line carries a **customer ID**, product/colour/size, qty, date, price?
- [ ] **History depth:** exact **earliest date** available (they said "as far as Fastmag" — get the real cutoff)
- [ ] **Cost / purchase price** (confirm their answer):
  - Historical → **reception price incl. duties** (receptions / `mouvements` table)
  - Forecast → product attribute **`Prix_Achat`**
  - → confirm which table/column each sits in
- [ ] **Customers:** can we pull the **full list with region + category in one query**? (`recherche-clients.do` is one-by-one only)

## 3. API-key permissions

- [ ] `api_query` — **critical** (history, cost, customers)
- [ ] `api_stock` — current inventory via `image-full-stocks.do` (net-to-order)
- [ ] `api_catalogue` — product master + selling price
- [ ] `api_logistique` — incoming / pipeline stock
- [ ] `api_recherche_clients` — fallback single lookups

## 4. Setup basics

- [ ] Base URL / domain
- [ ] Our **`enseigne`** value
- [ ] Test / sandbox dataset
- [ ] Rate limits

---

*Bottom line: `query.do` + schema unlocks the project. Everything else is secondary.*
