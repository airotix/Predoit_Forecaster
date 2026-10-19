"""Unit tests for the Joolan ERP client — guards & payload parsing (no network)."""

import pytest

from preduit_engine.erp_joolan import JoolanClient, ErpNotConfigured, ErpError


def test_requires_credentials():
    with pytest.raises(ErpNotConfigured):
        JoolanClient(base_url="", enseigne="", api_key="")
    with pytest.raises(ErpNotConfigured):
        JoolanClient(base_url="https://x", enseigne="acme", api_key="")


def test_unwrap_variants():
    # bare list
    assert JoolanClient._unwrap([{"a": 1}]) == [{"a": 1}]
    # {result: ok, data: [...]}
    assert JoolanClient._unwrap({"result": "ok", "data": [{"a": 1}]}) == [{"a": 1}]
    # single dict data is wrapped in a list
    assert JoolanClient._unwrap({"data": {"a": 1}}) == [{"a": 1}]


def test_unwrap_error_raises():
    with pytest.raises(ErpError):
        JoolanClient._unwrap({"result": "ko", "error_message": "invalid api key"})
    with pytest.raises(ErpError):
        JoolanClient._unwrap("not a payload")


def test_empty_sql_guards():
    client = JoolanClient(base_url="https://x", enseigne="acme", api_key="k")
    with pytest.raises(ErpNotConfigured):
        client.fetch_sales_history("")
    with pytest.raises(ErpNotConfigured):
        client.fetch_costs("")
