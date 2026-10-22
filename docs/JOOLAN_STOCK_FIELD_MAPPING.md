# Joolan warehouse stock and planning quantities

The client report uses five stock measures at article / colour / size / warehouse level:

- **Stock**: `En_Stock`, physical stock. Never label `Disponible` as physical stock.
- **À recevoir**: `Reliquat_Fournisseur`, outstanding supplier receipts across dates.
- **Clients**: `En_Commande`, outstanding customer-order units, not a customer count or season-booking total.
- **Attribué**: `Attribue`, allocated units. Do not deduct this again from `Disponible`.
- **Théorique**: `Theorique`, Joolan's recorded theoretical stock balance. Preserve negative balances; never substitute the demand forecast.

`Disponible` is shown separately as available stock. In the inspected export,
`En_Stock + Reliquat_Fournisseur - En_Commande - Attribue` reconciles to `Theorique`.
Display the source value rather than recomputing it from these fields: other ERP
buckets and future schema changes must not silently alter its meaning.

## Main projection layout

The default colour/size matrix retains the six planning rows: Available stock,
Incoming supply, Season booked units, Delivered against season bookings, Forecast
demand and Net purchase quantity. Incoming supply displays the full Joolan
`Reliquat_Fournisseur` (À recevoir), as requested by the client. Available stock
uses `Disponible`. Bookings, deliveries, forecast and net purchasing retain their
published quantities. The main matrix contains forecasted variants; additional
catalogue-only sizes do not turn known forecast totals into incomplete totals.

The five ERP source measures and date-eligible receipts are in a collapsed **Joolan
stock details and receipt eligibility** section below the main matrix. There is
no vertically scrolling container hiding forecast and net-purchase rows. The page
explains that full À recevoir includes receipts outside the planning dates, so it
is not automatically the receipt deduction used for net purchasing.

## Snapshot provenance and coverage

`projection_detail.detail` adds `warehouseStock` to the existing response. Existing
forecast/planning fields retain their meanings. `stock_snapshot.read` reads only
the export named by the published forecast's `freshRun`, using the primary
warehouse roles saved in that forecast's operating scope. It does not use a newer
active export or pool faulty, clearance or consignment warehouses.

The stock section displays warehouses, capture time and extraction source.
Duplicate records, absent fields and absent warehouse records remain unknown.
Per-measure full totals are unknown if any included variant is unknown. Recorded
subtotals are explicitly labelled as partial. Catalogue variants from the same
snapshot can be displayed without inventing forecasts for those identities.

## Separate planning quantities

The date-filtered outstanding supplier quantities remain labelled **Receipts
within planning period**. They are not renamed À recevoir. Season bookings,
delivered quantities, demand forecasts and net purchase quantities remain separate.
The projection list labels its booking-date quantities **Season bookings**.

Net purchasing still uses outstanding customer deliveries due in the planning
period plus additional unbooked forecast demand, minus available stock and eligible
scheduled receipts, floored at zero. The stock-label correction does not add ERP
customer balances to demand or subtract allocations twice. Budget, recommendation
and PO draft quantities are not overwritten by displaying these balances.

## New exports

The inventory field contract includes `En_Commande` and `Theorique`. If the full
stock endpoint omits these fields and the discovered Query API stocks schema
contains them, extraction uses the complete stocks query for one coherent set of
balances. Sparse query records remain sparse: absent variants are not assumed zero.

For article 101126 in the saved 2026-10-19 CENTRAL export, À recevoir is 405 BLACK
and 719 DARK COGNAC. These are balances from that export, not a claim that all other
values match the client's undated screenshot or today's live Joolan records.
