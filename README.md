# Predoit Forecaster

Demand planning and purchasing decision support for Daytona 73 and Iron and Resin.

The current application uses a Next.js frontend and the `backend-ai` FastAPI
service. It imports fresh Joolan data, keeps a durable SKU catalogue, produces
seasonal demand forecasts and supports this buying workflow:

**Budget Tracker → editable supplier PO → Order Validation → final CSV/PDF.**

Suppliers, quantities and prices can be reviewed and edited. Financial checks
cover costs, turnover, margins, existing commitments and the buying budget.
Validation is local; the software does not automatically send orders to Joolan
or suppliers.

## Setup and run

Follow [Quick Start](QUICK_START.md) for the current local runtime, prerequisites,
environment configuration and startup commands. Copy the supplied environment
templates and enter credentials locally. Keep the Joolan API key server-side.

The repository contains source code, tests and documentation. Databases, client
exports, generated forecasts, credentials, installed dependencies and build
outputs are excluded. A new machine needs its own configuration and a fresh
Joolan export or separately transferred authorized data.

## Documentation

- [Client deliverables](CLIENT_DELIVERABLES.md)
- [Supplier PO workflow](docs/PURCHASE_ORDERS.md)
- [Purchasing input reconciliation](docs/PURCHASING_INPUT_RECONCILIATION.md)
- [Order-based catalogue prices](docs/ORDER_PRICES.md)
- [Delivery readiness and remaining work](docs/DELIVERY_READINESS_2026-10-19.md)

Current status: supervised pilot. The readiness review documents remaining
forecast-quality, data-reconciliation, authentication and operational work before
production handover.
