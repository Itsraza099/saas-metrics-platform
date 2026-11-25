from fastapi.testclient import TestClient

from saas_metrics.source.simulator import Simulator


def _all_pages(api: TestClient, resource: str, **params: str | int) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    query: dict[str, str | int] = {"limit": 7, **params}
    while True:
        body = api.get(f"/v1/{resource}", params=query).json()
        rows += body["data"]
        if not body["has_more"]:
            return rows
        query = {"limit": 7, "cursor": body["next_cursor"]}


def test_paging_returns_every_row_exactly_once(api: TestClient, source: Simulator) -> None:
    rows = _all_pages(api, "invoices")
    ids = [r["id"] for r in rows]
    (count,) = source.conn.execute("select count(*) from invoices").fetchone()
    assert len(ids) == len(set(ids)) == count


def test_rows_are_ordered_by_updated_at_then_id(api: TestClient) -> None:
    rows = _all_pages(api, "subscriptions")
    keys = [(r["updated_at"], r["id"]) for r in rows]
    assert keys == sorted(keys, key=lambda k: (str(k[0]), str(k[1])))


def test_updated_since_is_inclusive(api: TestClient) -> None:
    rows = _all_pages(api, "customers")
    boundary = rows[len(rows) // 2]["updated_at"]
    since = _all_pages(api, "customers", updated_since=str(boundary))
    assert since[0]["updated_at"] == boundary
    assert all(str(r["updated_at"]) >= str(boundary) for r in since)


def test_unknown_resource_and_bad_cursor(api: TestClient) -> None:
    assert api.get("/v1/payments").status_code == 404
    assert api.get("/v1/invoices", params={"cursor": "not-a-cursor"}).status_code == 400
    assert api.get("/v1/invoices", params={"limit": 0}).status_code == 422
