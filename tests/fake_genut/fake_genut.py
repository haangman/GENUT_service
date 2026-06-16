#!/usr/bin/env python
"""실 GENUT를 모사하는 fake CLI (stdlib만 사용).

실 GENUT와 동일한 플래그/.env 계약을 따른다:
- 함수당 positive:negative = 50:50 테스트를 out 폴더에 생성
- --function-name, --debug, --enable-assure 반영
- .env(cwd)에서 TEST_GENERATION_MODE 등을 읽어 result.json의 env_seen에 기록
- 시나리오는 소스 파일에서 위로 올라가며 찾은 GENUT_SCENARIO.json으로 구동
  (outcome: success | hard_fail | crash, tests_per_function: int)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

EXT = {"c": ".c", "cpp": ".cpp", "kunit": ".c"}


def find_scenario(file_list: list[str]) -> dict:
    for src in file_list:
        directory = Path(src).resolve().parent
        for _ in range(6):
            candidate = directory / "GENUT_SCENARIO.json"
            if candidate.is_file():
                try:
                    return json.loads(candidate.read_text(encoding="utf-8-sig"))
                except (json.JSONDecodeError, OSError):
                    return {}
            if directory.parent == directory:
                break
            directory = directory.parent
    return {}


def read_env(cwd: str) -> dict:
    env: dict[str, str] = {}
    path = Path(cwd) / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def extract_functions(src_path: str) -> list[str]:
    try:
        text = Path(src_path).read_text(encoding="utf-8")
    except OSError:
        return []
    functions = re.findall(r"@genut-fn:\s*(\w+)", text)
    return functions or [Path(src_path).stem]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file-list", required=True)
    parser.add_argument("--compile-db-path", required=True)
    parser.add_argument("--out-test-folder-path", required=True)
    parser.add_argument("--max-attempts", type=int, default=10)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--enable-assure", action="store_true")
    parser.add_argument("--function-name", default=None)
    args = parser.parse_args(argv)

    file_list = [
        line.strip()
        for line in Path(args.file_list).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    scenario = find_scenario(file_list)
    outcome = scenario.get("outcome", "success")
    per_fn = int(scenario.get("tests_per_function", 1))
    env = read_env(os.getcwd())
    mode = env.get("TEST_GENERATION_MODE", "cpp")
    ext = EXT.get(mode, ".cpp")

    out = Path(args.out_test_folder_path)
    out.mkdir(parents=True, exist_ok=True)

    if args.debug:
        (out / "genut_debug.log").write_text("genut debug log\n", encoding="utf-8")

    if outcome == "crash":
        sys.stderr.write("simulated crash\n")
        sys.exit(int(scenario.get("exit_code", 3)))

    # 시나리오로 실행 시간을 조절(병렬 실행/실시간 로그 관측용). 기본 0.
    total = float(scenario.get("sleep_seconds", 0))
    if total > 0:
        steps = max(1, int(round(total)))
        for i in range(steps):
            time.sleep(total / steps)
            print(f"[genut] generating tests... {i + 1}/{steps}", flush=True)

    functions: list[str] = []
    generated: list[str] = []
    positive = negative = 0
    for src in file_list:
        fns = extract_functions(src)
        if args.function_name:
            fns = [fn for fn in fns if fn == args.function_name]
        for fn in fns:
            functions.append(fn)
            for index in range(per_fn):
                for kind in ("pos", "neg"):
                    name = f"test_{fn}_{index:03d}_{kind}{ext}"
                    (out / name).write_text(f"// {kind} test for {fn}\n", encoding="utf-8")
                    generated.append(name)
                    if kind == "pos":
                        positive += 1
                    else:
                        negative += 1

    if args.enable_assure:
        assure_dir = out / "assure"
        assure_dir.mkdir(exist_ok=True)
        (assure_dir / "assure_summary.json").write_text(
            json.dumps({"quality": "ok"}), encoding="utf-8"
        )

    status = "failed" if outcome == "hard_fail" else "success"
    result = {
        "status": status,
        "mode": mode,
        "functions": functions,
        "generated_files": generated,
        "counts": {"positive": positive, "negative": negative, "total": positive + negative},
        "attempts_used": int(scenario.get("attempts_used", 1)),
        "max_attempts": args.max_attempts,
        "enable_assure": args.enable_assure,
        "env_seen": {
            key: env.get(key)
            for key in ("TEST_GENERATION_MODE", "DS_ASSIST_SEND_SYSTEM_NAME", "TEST_RUN_CMD")
        },
        "file_list_seen": file_list,
        "compile_db_seen": args.compile_db_path,
    }
    (out / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"success": status == "success", "status": status}))
    sys.exit(0 if status == "success" else 1)


if __name__ == "__main__":
    main()
