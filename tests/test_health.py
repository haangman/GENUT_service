"""M0: 앱 부팅 및 헬스 체크."""

from __future__ import annotations


def test_health_ok(client) -> None:
    """/health 가 200과 status=ok 를 반환한다."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
