"""Gerrit change 주소로 패치 diff를 가져오는(fetch-gerrit-patch) API 테스트.

로컬 git repo에 refs/changes/<XX>/<num>/<ps> ref를 직접 만들어 가상 Gerrit로 쓴다
(fetch/ls-remote는 로컬 경로에도 동일하게 동작).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from genut_service.services.gerrit_patch_service import (
    GerritChangeInputError,
    change_ref,
    parse_change_input,
)


def _git(*args: str, cwd: Path) -> str:
    res = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return res.stdout.strip()


@pytest.fixture()
def gerrit_repo(tmp_path: Path) -> dict:
    """change 1234의 패치셋 1·2와 meta ref를 가진 가상 Gerrit origin repo."""
    origin = tmp_path / "gerrit-origin"
    origin.mkdir()
    _git("-c", "init.defaultBranch=main", "init", cwd=origin)
    _git("config", "user.email", "t@t", cwd=origin)
    _git("config", "user.name", "t", cwd=origin)
    (origin / "src").mkdir()
    (origin / "src" / "mod.c").write_text("int f(void) { return 1; }\n", encoding="utf-8")
    _git("add", "-A", cwd=origin)
    _git("commit", "-m", "init", cwd=origin)
    base = _git("rev-parse", "HEAD", cwd=origin)

    # 패치셋 1: g() 추가(v1) / 패치셋 2: 개선판(v2) — 각각 refs/changes/34/1234/<ps>
    _git("checkout", "-b", "change-1234", cwd=origin)
    (origin / "src" / "mod.c").write_text(
        "int f(void) { return 1; }\nint g(void) { return 1; } /* v1 */\n", encoding="utf-8"
    )
    _git("add", "-A", cwd=origin)
    _git("commit", "-m", "Add g() helper", cwd=origin)
    _git("update-ref", "refs/changes/34/1234/1", "HEAD", cwd=origin)
    (origin / "src" / "mod.c").write_text(
        "int f(void) { return 1; }\nint g(void) { return 2; } /* v2 */\n", encoding="utf-8"
    )
    _git("add", "-A", cwd=origin)
    _git("commit", "--amend", "-m", "Add g() helper", cwd=origin)
    _git("update-ref", "refs/changes/34/1234/2", "HEAD", cwd=origin)
    # meta ref(비숫자 패치셋)는 최신 패치셋 선택에서 제외돼야 한다
    _git("update-ref", "refs/changes/34/1234/meta", base, cwd=origin)
    _git("checkout", "main", cwd=origin)
    _git("branch", "-D", "change-1234", cwd=origin)
    return {"origin": origin}


def _clone(origin: Path, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", str(origin), str(dest)],
        check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _payload(origin: Path, dest: Path, change: str) -> dict:
    return {"git_url": str(origin), "code_path": str(dest), "change": change}


# ---------- 주소 파서 단위 ----------

@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1234", (1234, None)),
        ("1234/5", (1234, 5)),
        ("https://gerrit.example.com/c/platform/prod/+/1234", (1234, None)),
        ("https://gerrit.example.com/c/platform/prod/+/1234/5", (1234, 5)),
        # 파일 보기 화면 URL(패치셋 뒤에 경로가 붙음)도 허용
        ("https://gerrit.example.com/c/platform/prod/+/1234/5/src/mod.c", (1234, 5)),
        ("https://gerrit.example.com/c/prod/+/1234?tab=comments", (1234, None)),
        ("https://gerrit.example.com/#/c/1234/5", (1234, 5)),
        ("  1234/5  ", (1234, 5)),
    ],
)
def test_parse_change_input(text: str, expected: tuple[int, int | None]) -> None:
    assert parse_change_input(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "abc", "https://gerrit.example.com/q/status:open"])
def test_parse_change_input_rejects_bad_input(text: str) -> None:
    with pytest.raises(GerritChangeInputError):
        parse_change_input(text)


def test_change_ref_pads_last_two_digits() -> None:
    assert change_ref(1234, 5) == "refs/changes/34/1234/5"
    assert change_ref(7, 1) == "refs/changes/07/7/1"  # 한 자리 change도 두 자리 패딩


# ---------- API ----------

def test_fetch_latest_patchset_by_number(
    client: TestClient, gerrit_repo: dict, tmp_path: Path
) -> None:
    """패치셋 미지정이면 최신(2)을 선택한다(meta ref 제외)."""
    dest = tmp_path / "checkout"
    _clone(gerrit_repo["origin"], dest)

    resp = client.post(
        "/api/products/fetch-gerrit-patch", json=_payload(gerrit_repo["origin"], dest, "1234")
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "gerrit-1234-2"
    assert body["ref"] == "refs/changes/34/1234/2"
    assert body["subject"] == "Add g() helper"
    assert "/* v2 */" in body["content"]
    assert "diff --git" in body["content"]


def test_fetch_explicit_patchset_and_url_form(
    client: TestClient, gerrit_repo: dict, tmp_path: Path
) -> None:
    """URL 형식 + 패치셋 지정 시 그 패치셋(1)의 diff를 가져온다."""
    dest = tmp_path / "checkout"
    _clone(gerrit_repo["origin"], dest)

    resp = client.post(
        "/api/products/fetch-gerrit-patch",
        json=_payload(
            gerrit_repo["origin"], dest, "https://gerrit.example.com/c/platform/prod/+/1234/1"
        ),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "gerrit-1234-1"
    assert "/* v1 */" in body["content"]
    assert "/* v2 */" not in body["content"]


def test_fetched_content_round_trips_through_pull_code_patches(
    client: TestClient, gerrit_repo: dict, tmp_path: Path
) -> None:
    """가져온 content를 그대로 패치로 등록하면 다운로드에서 적용된다(통합 왕복)."""
    dest = tmp_path / "checkout"
    _clone(gerrit_repo["origin"], dest)
    fetched = client.post(
        "/api/products/fetch-gerrit-patch", json=_payload(gerrit_repo["origin"], dest, "1234")
    ).json()

    dest2 = tmp_path / "checkout2"
    resp = client.post(
        "/api/products/pull-code",
        json={
            "git_url": str(gerrit_repo["origin"]),
            "git_ref": "main",
            "code_path": str(dest2),
            "patches": [{"name": fetched["name"], "content": fetched["content"], "order_index": 0}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert "/* v2 */" in (dest2 / "src" / "mod.c").read_text(encoding="utf-8")


def test_fetch_requires_existing_checkout(
    client: TestClient, gerrit_repo: dict, tmp_path: Path
) -> None:
    resp = client.post(
        "/api/products/fetch-gerrit-patch",
        json=_payload(gerrit_repo["origin"], tmp_path / "no-checkout", "1234"),
    )
    assert resp.status_code == 400
    assert "먼저 다운로드" in resp.json()["detail"]


def test_fetch_unknown_change_returns_400(
    client: TestClient, gerrit_repo: dict, tmp_path: Path
) -> None:
    dest = tmp_path / "checkout"
    _clone(gerrit_repo["origin"], dest)
    resp = client.post(
        "/api/products/fetch-gerrit-patch", json=_payload(gerrit_repo["origin"], dest, "9999")
    )
    assert resp.status_code == 400
    assert "9999" in resp.json()["detail"]


def test_fetch_bad_change_text_returns_400(
    client: TestClient, gerrit_repo: dict, tmp_path: Path
) -> None:
    dest = tmp_path / "checkout"
    _clone(gerrit_repo["origin"], dest)
    resp = client.post(
        "/api/products/fetch-gerrit-patch", json=_payload(gerrit_repo["origin"], dest, "abc")
    )
    assert resp.status_code == 400


def test_fetch_conflicts_while_job_running(
    client: TestClient, db_session, gerrit_repo: dict, tmp_path: Path
) -> None:
    """같은 code_path를 쓰는 프로덕트의 job 실행 중이면 409(pull-code와 공용 가드)."""
    from genut_service.db.models import GenutInstance, Job, Product, ProductLock

    dest = tmp_path / "busy-checkout"
    _clone(gerrit_repo["origin"], dest)
    product = Product(
        name="busy",
        product_code="B-1",
        git_url=str(gerrit_repo["origin"]),
        compile_db_rel="build",
        out_tests_rel="tests/generated",
        cmake_configure_cmd="c",
        cmake_build_cmd="b",
        test_run_cmd="r",
        test_generation_mode="cpp",
        code_path=str(dest),
    )
    worker = GenutInstance(
        name="w",
        repo_url="u",
        ds_assist_credential_key="k",
        ds_assist_send_system_name="s",
    )
    db_session.add_all([product, worker])
    db_session.flush()
    job = Job(product_id=product.id, status="running")
    db_session.add(job)
    db_session.flush()
    db_session.add(
        ProductLock(product_id=product.id, job_id=job.id, genut_instance_id=worker.id)
    )
    db_session.commit()

    resp = client.post(
        "/api/products/fetch-gerrit-patch", json=_payload(gerrit_repo["origin"], dest, "1234")
    )
    assert resp.status_code == 409
