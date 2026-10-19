# Catalogue active/inactive status

The initial article status comes from Joolan `produits.Actif`; the initial
colour/size status comes from `skus.Actif`. This implementation interprets `1`
as active and `0` as inactive for new purchasing, as agreed with the user.
Other/missing values remain **Unknown** and are not silently made inactive.
Source values are read from the latest saved validated export. Use Season Setup
to fetch newer Joolan records; changing a status never writes back to Joolan.

## Catalogue controls

Open an article to change its article status. Each size/SKU also has a status
selector. Choices are **Use Joolan**, **Active — local override**, and
**Inactive — no purchasing**. Changes save immediately. An optional reason is
recorded, and the SKU Details panel shows local article/SKU status history.
Save/discard pending price edits before changing status.

- An inactive article blocks every colour and size, even if a SKU is active.
- An active article can have inactive individual SKUs; those remain blocked.
- To reactivate everything, activate the article and review individual SKU flags.
- Local overrides survive exports and new forecasts. **Use Joolan** removes only
  that override and follows the latest exported flag again.
- The status filter finds matching variants/articles; an article's displayed
  breakdown still includes all its colours and sizes.
- Neither historical orders, catalogue prices, stock nor demand forecasts are
  deleted or zeroed by an inactive status.

## Purchase workflow

New purchase recommendations and Budget Tracker draft quantities default to zero
for inactive items. They remain visible with their forecast and an inactive reason.
Inactive positive quantities cannot receive financial validation, count toward
the eligible budget allocation, or be imported into a new supplier PO.

Existing saved drafts and POs retain their snapshots. A status change makes the
budget source stale; saved positive quantities receive inactive blockers until
the user sets them to zero or changes the Catalogue status. Existing POs display
current inactive warnings without rewriting their lines. PO documents are local
drafts, and this feature does not send or cancel any real supplier orders.

The shared event stream notifies open pages of Catalogue status changes. Server
validation always checks current status even when a browser has not refreshed.

## Storage

- `catalogue_article_status` / `catalogue_sku_status`: normalized Joolan source flags.
- `catalogue_status_overrides`: durable local overrides per article or SKU.
- `catalogue_status_history`: timestamped changes, prior overrides and optional reasons.
- `catalogue_effective_status`: view applying article/SKU precedence for filtering.
- `planning_state`: source fingerprint and local status-change marker.

These tables are independent of forecast publication. Status is not scoped by
currency or season. No default override is created during initial import.

Verification: `backend-ai/tests/test_catalogue_status.py` covers source flags,
precedence, manual persistence/reset, missing flags, article pagination/filtering,
zero purchase defaults with unchanged demand, positive-draft blockers, atomic
validation, history/reopening, and protection of existing PO snapshots.
