"""Generate the source-code listing required for software copyright registration.

China's software copyright registration asks for the first 30 and last 30 pages of the
source code at 50 lines per page, with a continuous page footer. Assembling that by hand is
error-prone and has to be redone every time the code changes, so it is generated here.

Two decisions worth stating:

* **Nothing is excluded to make the listing look better.** Files are collected in a fixed,
  documented order and the listing reflects the repository as it is. What *is* excluded is
  anything that could leak a secret (``.env``, key material) or that is not our code
  (``node_modules``, build output, dependency lock files) — the registration covers the
  applicant's own source, and shipping a credential to a government filing is unforgivable.
* **The scan for secrets is a safety net, not a guarantee.** It reports suspicious lines and
  refuses to write the listing unless ``--allow-suspicious`` is passed. A human still has to
  read the 60 pages before filing; the registration is a legal statement, not a build
  artifact.

Usage::

    python scripts/build_copyright_listing.py
    python scripts/build_copyright_listing.py --out ../docs/ip/software-copyright/源程序.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LINES_PER_PAGE = 50
PAGES_EACH_END = 30

# Collection order is fixed so the listing is reproducible and reviewable: entry point and
# configuration first, then the algorithm packages the registration is really about, then
# the API surface, then the frontend.
INCLUDE_GLOBS: tuple[tuple[str, str], ...] = (
    ("backend", "app/main.py"),
    ("backend", "app/core/*.py"),
    ("backend", "app/models/*.py"),
    ("backend", "app/schemas/*.py"),
    ("backend", "algorithms/identifiability/*.py"),
    ("backend", "algorithms/pipeline/*.py"),
    ("backend", "algorithms/agent/*.py"),
    ("backend", "algorithms/report/*.py"),
    ("backend", "algorithms/cleaning/*.py"),
    ("backend", "app/services/*.py"),
    ("backend", "app/api/*.py"),
    ("backend", "alembic/versions/*.py"),
    ("frontend", "src/*.ts"),
    ("frontend", "src/api/*.ts"),
    ("frontend", "src/stores/*.ts"),
    ("frontend", "src/router/*.ts"),
    ("frontend", "src/types/*.ts"),
    ("frontend", "src/components/*.vue"),
    ("frontend", "src/layouts/*.vue"),
    ("frontend", "src/views/*.vue"),
)

# Excluded because it is not ours, is generated, or must never reach a public filing.
EXCLUDE_PARTS = ("node_modules", "dist", "__pycache__", ".venv", "data")
EXCLUDE_NAMES = (".env", ".env.local", "package-lock.json", "openapi.json")

# Deliberately blunt: a false positive costs one human glance, a false negative costs a
# credential published in a government filing.
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|passwd|password|token)\s*[:=]\s*['\"][^'\"]{6,}"),
    re.compile(r"(?i)postgresql\+asyncpg://[^\s'\"]*:[^\s'\"@]+@"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\bsk-[a-z0-9]{16,}"),
)
# Defaults that are public by design; flagging them trains the reader to ignore the warning.
SECRET_ALLOWLIST = (
    "indusopt:indusopt@",
    'llm_api_key: str = Field(default=""',
    "INDUSOPT_LLM_API_KEY",
)


def collect_files() -> list[Path]:
    seen: list[Path] = []
    for area, pattern in INCLUDE_GLOBS:
        base = REPO_ROOT / area
        for path in sorted(base.glob(pattern)):
            if not path.is_file():
                continue
            if any(part in EXCLUDE_PARTS for part in path.parts):
                continue
            if path.name in EXCLUDE_NAMES:
                continue
            if path not in seen:
                seen.append(path)
    return seen


def iter_lines(files: list[Path]) -> Iterator[str]:
    """Yield every source line, prefixed by a file banner so pages stay navigable."""

    for path in files:
        relative = path.relative_to(REPO_ROOT)
        yield f"{'=' * 78}"
        yield f"==== {relative}"
        yield f"{'=' * 78}"
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                yield line.rstrip("\n")


def find_suspicious(files: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in files:
        relative = path.relative_to(REPO_ROOT)
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                if any(allowed in line for allowed in SECRET_ALLOWLIST):
                    continue
                if any(pattern.search(line) for pattern in SECRET_PATTERNS):
                    findings.append(f"{relative}:{number}: {line.strip()[:100]}")
    return findings


def paginate(lines: list[str]) -> list[list[str]]:
    return [lines[start : start + LINES_PER_PAGE] for start in range(0, len(lines), LINES_PER_PAGE)]


def render(pages: list[list[str]], *, total_pages: int, total_lines: int) -> str:
    """Render the selected pages with the continuous numbering the filing expects."""

    selected: list[tuple[int, list[str]]]
    if total_pages <= PAGES_EACH_END * 2:
        # Short enough that the whole listing is submitted; the "first 30 / last 30" rule
        # only bites when the program is longer than 60 pages.
        selected = list(enumerate(pages, start=1))
        note = f"源程序共 {total_pages} 页，未超过 60 页，按规定提交全部页。"
    else:
        head = list(enumerate(pages[:PAGES_EACH_END], start=1))
        tail_start = total_pages - PAGES_EACH_END + 1
        tail = list(enumerate(pages[-PAGES_EACH_END:], start=tail_start))
        selected = head + tail
        note = (
            f"源程序共 {total_pages} 页（{total_lines} 行，每页 {LINES_PER_PAGE} 行）。"
            f"按规定提交前 {PAGES_EACH_END} 页（第 1–{PAGES_EACH_END} 页）与"
            f"后 {PAGES_EACH_END} 页（第 {tail_start}–{total_pages} 页），中间页略。"
        )

    out: list[str] = [
        "IndusOpt 工模智优 —— 计算机软件著作权登记 源程序",
        note,
        "",
    ]
    previous = 0
    for number, page in selected:
        if previous and number != previous + 1:
            out.append(f"（此处略去第 {previous + 1}–{number - 1} 页）")
            out.append("")
        out.extend(page)
        out.append("")
        out.append(f"—— 第 {number} 页 / 共 {total_pages} 页 ——")
        out.append("")
        previous = number
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO_ROOT / "docs/ip/software-copyright/源程序.txt",
    )
    parser.add_argument(
        "--allow-suspicious",
        action="store_true",
        help="即使检出疑似敏感内容也照常写出（须先人工确认为误报）。",
    )
    arguments = parser.parse_args()

    files = collect_files()
    if not files:
        print("没有收集到任何源文件，请检查 INCLUDE_GLOBS 与仓库路径。", file=sys.stderr)
        return 1

    suspicious = find_suspicious(files)
    if suspicious:
        print(f"检出 {len(suspicious)} 处疑似敏感内容：", file=sys.stderr)
        for item in suspicious[:40]:
            print(f"  {item}", file=sys.stderr)
        if not arguments.allow_suspicious:
            print(
                "\n未写出清单。请逐条确认后修正，或确认全部为误报后加 --allow-suspicious 重跑。",
                file=sys.stderr,
            )
            return 2

    lines = list(iter_lines(files))
    pages = paginate(lines)
    text = render(pages, total_pages=len(pages), total_lines=len(lines))
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(text, encoding="utf-8")

    print(f"源文件 {len(files)} 个，合计 {len(lines)} 行，{len(pages)} 页。")
    print(f"已写出 {arguments.out}")
    print("提交前请人工翻阅全部 60 页，确认无主机名、口令或第三方私有信息。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
