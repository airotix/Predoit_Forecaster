"""
Joolan / Lisa ERP connector.

Talks to the Joolan API v2 (https://lisa.joolan.com/api/v2). Auth is via two query
parameters on every call: `enseigne` (database name) and `api-key`.

This client is intentionally configuration-driven so it can be wired up now and switched
on later, once real credentials exist, with zero code changes:

- Stock uses the fully-documented `/image-full-stocks.do` endpoint.
- Sales history and per-unit cost use `/query.do` (read-only SQL). Because we don't yet
  know Joolan's exact table/column names, the SQL is supplied via configuration
  (`history_sql` / `cost_sql`). The SQL is expected to alias its output columns to the
  names the forecasting pipeline consumes (e.g. `... AS "Référence"`).

The API key is passed as a query parameter (Joolan's requirement); callers must only use
HTTPS and must never log full request URLs.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


class ErpNotConfigured(Exception):
    """Raised when the ERP connection is not fully configured."""


class ErpError(Exception):
    """Raised when the ERP returns an error or an unexpected payload."""


class JoolanClient:
    def __init__(
        self,
        base_url: str,
        enseigne: str,
        api_key: str,
        magasins: Optional[str] = None,
        timeout: float = 60.0,
    ):
        if not (base_url and enseigne and api_key):
            raise ErpNotConfigured(
                "Joolan ERP is not configured (base URL, enseigne and API key are all required)."
            )
        self.base_url = base_url.rstrip("/")
        self.enseigne = enseigne
        self.api_key = api_key
        self.magasins = magasins or None
        self.timeout = timeout

    # ── low-level ─────────────────────────────────────────────────────────
    def _auth_params(self) -> dict:
        return {"enseigne": self.enseigne, "api-key": self.api_key}

    def _get(self, endpoint: str, params: Optional[dict] = None):
        import httpx

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        merged = {**self._auth_params(), **(params or {})}
        # NOTE: never log `url`/`merged` — they contain the API key.
        resp = httpx.get(url, params=merged, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _post_text(self, endpoint: str, body: str, params: Optional[dict] = None):
        import httpx

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        merged = {**self._auth_params(), **(params or {})}
        resp = httpx.post(
            url, params=merged, content=body,
            headers={"Content-Type": "text/plain"}, timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _unwrap(payload) -> list:
        """Joolan wraps list results as {result: ok|ko, data: [...]}."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            if payload.get("result") == "ko":
                raise ErpError(payload.get("error_message") or "ERP returned an error.")
            data = payload.get("data")
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        raise ErpError("Unexpected ERP response shape.")

    # ── health ────────────────────────────────────────────────────────────
    def test_connection(self) -> dict:
        """Cheap round-trip to verify credentials. Uses a trivial SQL SELECT."""
        rows = self.run_sql("SELECT 1 AS ok")
        return {"ok": True, "rows": len(rows)}

    # ── read: SQL (query.do) ─────────────────────────────────────────────
    def run_sql(self, sql: str) -> list:
        """Execute a read-only SELECT via /query.do and return a list of dict rows."""
        return self._unwrap(self._post_text("query.do", sql))

    def fetch_sales_history(self, history_sql: str) -> pd.DataFrame:
        """Pull the demand history. `history_sql` must SELECT columns aliased to the names
        the pipeline expects (Référence, Couleur, Taille, Client, LIV_qte, RELIQUAT_qte,
        Prix, Saison, STOCK, ...)."""
        if not history_sql:
            raise ErpNotConfigured("No ERP history query configured (FORECASTER_ERP_HISTORY_SQL).")
        return pd.DataFrame(self.run_sql(history_sql))

    def fetch_costs(self, cost_sql: str) -> pd.DataFrame:
        """Pull per-unit purchase cost. `cost_sql` should return Produit, Couleur, Taille,
        Prix_Achat (or aliases the caller expects)."""
        if not cost_sql:
            raise ErpNotConfigured("No ERP cost query configured (FORECASTER_ERP_COST_SQL).")
        return pd.DataFrame(self.run_sql(cost_sql))

    # ── read: stock (image-full-stocks.do) ───────────────────────────────
    def fetch_stock(self) -> pd.DataFrame:
        """Full stock image (all SKUs × stores). Documented schema — no SQL needed."""
        params = {}
        if self.magasins:
            params["Magasins"] = self.magasins
        return pd.DataFrame(self._unwrap(self._get("image-full-stocks.do", params)))

    # ── read: product catalogue (catalogue-web.do) ───────────────────────
    def fetch_catalogue(self, last_call: Optional[str] = None) -> pd.DataFrame:
        params = {"output-format": "json"}
        if last_call:
            params["last-call"] = last_call
        if self.magasins:
            # catalogue-web takes a single Magasin; use the first if a list was given.
            params["Magasin"] = self.magasins.split(";")[0]
        return pd.DataFrame(self._unwrap(self._get("catalogue-web.do", params)))
