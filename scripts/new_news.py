#!/usr/bin/env python3
"""Create one AQ Portal news article and refresh its navigation and landing card."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
from typing import Optional, Tuple
import unicodedata


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LANDING_PAGE = PROJECT_ROOT / "docs" / "index.md"
NEWS_INDEX = PROJECT_ROOT / "docs" / "news" / "index.md"
NEWS_DIRECTORY = PROJECT_ROOT / "docs" / "news"
DRAFT_DIRECTORY = PROJECT_ROOT / "news-drafts"
BUILD_DIRECTORY = PROJECT_ROOT / "build" / "html"

LATEST_START = "<!-- LATEST_NEWS_START -->"
LATEST_END = "<!-- LATEST_NEWS_END -->"
BODY_INSTRUCTION = (
    "<!-- Write the full news text below this line. "
    "This instruction is removed automatically. -->"
)

MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


class NewsError(RuntimeError):
    """A user-facing validation or publication-preparation error."""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a news page, add it to the News navigation, update the "
            "landing-page Latest news card, and run a strict Sphinx build."
        )
    )
    parser.add_argument("--date", help="Publication date in YYYY-MM-DD format")
    parser.add_argument("--title", help="News title")
    parser.add_argument("--summary", help="One-sentence landing-page summary")
    parser.add_argument("--source", help="Optional source URL")
    parser.add_argument(
        "--body-file",
        type=Path,
        help="Markdown file containing only the article body (skips editor)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the final confirmation (useful for scripted testing)",
    )
    return parser.parse_args()


def prompt_required(label: str, supplied: Optional[str] = None) -> str:
    value = supplied.strip() if supplied else ""
    while not value:
        value = input(f"{label}: ").strip()
        if not value:
            print("  A value is required.")
    return " ".join(value.split())


def prompt_date(supplied: Optional[str] = None) -> dt.date:
    default = dt.date.today().isoformat()
    value = supplied.strip() if supplied else ""
    while True:
        if not value:
            value = input(f"Publication date [{default}]: ").strip() or default
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            print("  Please use YYYY-MM-DD, for example 2026-08-13.")
            value = ""


def prompt_source(supplied: Optional[str] = None) -> str:
    if supplied is None:
        value = input("Source URL (optional): ").strip()
    else:
        value = supplied.strip()
    if value and not re.match(r"^https?://", value, flags=re.IGNORECASE):
        raise NewsError("The source URL must start with http:// or https://.")
    if ">" in value or "\n" in value:
        raise NewsError("The source URL contains unsupported characters.")
    return value


def slugify(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_title = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_title).strip("-")
    slug = slug[:90].rstrip("-")
    if not slug:
        raise NewsError("The title cannot be converted into a safe filename.")
    return slug


def display_date(value: dt.date) -> str:
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def article_prefix(title: str, publication_date: dt.date, source: str) -> str:
    lines = [f"# {title}", "", f"*Published: {publication_date.isoformat()}*  "]
    if source:
        lines.append(f"*Source: <{source}>*")
    return "\n".join(lines).rstrip() + "\n\n"


def open_draft_in_editor(path: Path) -> None:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        command = shlex.split(editor) + [str(path)]
        subprocess.run(command, check=True)
        return

    code = shutil.which("code")
    if code:
        subprocess.run([code, "--wait", str(path)], check=True)
        return

    if sys.platform == "darwin" and shutil.which("open"):
        visual_studio_code = Path("/Applications/Visual Studio Code.app")
        if visual_studio_code.exists():
            subprocess.Popen(["open", "-a", "Visual Studio Code", str(path)])
        else:
            subprocess.Popen(["open", str(path)])
        input("Edit and save the article, then press Return here to continue...")
        return

    terminal_editor = shutil.which("nano") or shutil.which("vi")
    if terminal_editor:
        subprocess.run([terminal_editor, str(path)], check=True)
        return

    print(f"Open this draft in an editor and save it:\n  {path}")
    input("Press Return after saving the article...")


def extract_body_from_draft(draft_text: str, draft_path: Path) -> str:
    """Extract body text without depending on an editor-preserved marker."""
    lines = draft_text.splitlines()
    last_header_line = -1

    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and stripped.startswith("# "):
            last_header_line = index
        elif stripped.startswith("*Published:") or stripped.startswith("*Source:"):
            last_header_line = index

    candidate = "\n".join(lines[last_header_line + 1 :])

    # Remove only leading HTML comments. This accepts the original long
    # instruction, a formatter-reflowed instruction, the shorter instruction,
    # or a draft from which the instruction was manually deleted.
    candidate = re.sub(r"^(?:\s*<!--.*?-->\s*)+", "", candidate, flags=re.DOTALL)
    body = candidate.strip()
    if not body:
        raise NewsError(
            "No article text was found in the draft. The draft has been "
            f"preserved at:\n  {draft_path}"
        )
    return body


def obtain_article_body(
    args: argparse.Namespace,
    filename: str,
    prefix: str,
) -> Tuple[str, Optional[Path]]:
    if args.body_file:
        body_file = args.body_file.expanduser().resolve()
        if not body_file.is_file():
            raise NewsError(f"Body file not found: {body_file}")
        body = body_file.read_text(encoding="utf-8").strip()
        if not body:
            raise NewsError("The supplied article body is empty.")
        return prefix + body + "\n", None

    DRAFT_DIRECTORY.mkdir(exist_ok=True)
    draft_path = DRAFT_DIRECTORY / filename
    if draft_path.exists():
        print(f"\nA preserved draft was found:\n  {draft_path}")
        answer = input("Reuse this draft? [Y/n]: ").strip().lower()
        if answer not in {"", "y", "yes"}:
            raise NewsError("News creation cancelled. The existing draft was preserved.")
        print("The preserved draft will reopen for checking.")
    else:
        draft_path.write_text(prefix + BODY_INSTRUCTION + "\n\n", encoding="utf-8")
        print("\nThe article draft will now open for editing.")
        print("Write the full news text below the instruction, then save it.")

    open_draft_in_editor(draft_path)

    draft_text = draft_path.read_text(encoding="utf-8")
    body = extract_body_from_draft(draft_text, draft_path)
    return prefix + body + "\n", draft_path


def verify_project() -> Tuple[str, str]:
    for path in (LANDING_PAGE, NEWS_INDEX, NEWS_DIRECTORY):
        if not path.exists():
            raise NewsError(f"Required project path not found: {path}")

    landing_text = LANDING_PAGE.read_text(encoding="utf-8")
    news_index_text = NEWS_INDEX.read_text(encoding="utf-8")

    if landing_text.count(LATEST_START) != 1 or landing_text.count(LATEST_END) != 1:
        raise NewsError(
            "The landing page does not contain exactly one Latest news marker pair."
        )
    if landing_text.index(LATEST_START) > landing_text.index(LATEST_END):
        raise NewsError("The Latest news markers are in the wrong order.")
    if "```{toctree}" not in news_index_text:
        raise NewsError("The News index does not contain a toctree.")

    sphinx_check = subprocess.run(
        [sys.executable, "-c", "import sphinx"],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if sphinx_check.returncode != 0:
        raise NewsError(
            "Sphinx is not available to this Python installation. "
            "Run the portal setup first."
        )
    return landing_text, news_index_text


def insert_news_entry(news_index_text: str, stem: str, publication_date: dt.date) -> str:
    if re.search(rf"(?m)^\s*{re.escape(stem)}\s*$", news_index_text):
        raise NewsError("This news item is already present in the News index.")

    lines = news_index_text.splitlines(keepends=True)
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "```{toctree}")
        end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "```")
    except StopIteration as exc:
        raise NewsError("The News toctree is malformed.") from exc

    first_entry = None
    insertion_point = None
    for i in range(start + 1, end):
        stripped = lines[i].strip()
        if stripped and not stripped.startswith(":"):
            first_entry = stripped
            insertion_point = i
            break

    if insertion_point is None:
        insertion_point = end
    elif re.match(r"^\d{4}-\d{2}-\d{2}-", first_entry or ""):
        newest_existing = dt.date.fromisoformat((first_entry or "")[:10])
        if publication_date < newest_existing:
            raise NewsError(
                "The publication date is older than the current latest news item "
                f"({newest_existing.isoformat()})."
            )

    lines.insert(insertion_point, stem + "\n")
    return "".join(lines)


def build_latest_block(
    stem: str,
    title: str,
    summary: str,
    publication_date: dt.date,
) -> str:
    safe_title = html.escape(title, quote=True)
    safe_summary = html.escape(summary, quote=True)
    date_text = html.escape(display_date(publication_date), quote=True)
    link = f"news/{stem}.html"
    return textwrap.dedent(
        f"""\
        {LATEST_START}
        <section class="landing-latest-news" aria-labelledby="latest-news-title">
          <div class="latest-news-heading">
            <h2 id="latest-news-title">Latest news</h2>
            <span class="latest-news-date">{date_text}</span>
          </div>
          <h3>
            <a href="{link}">{safe_title}</a>
          </h3>
          <p>{safe_summary}</p>
          <div class="latest-news-links">
            <a class="latest-news-read" href="{link}">Read the full news item →</a>
            <a href="news/index.html">All news</a>
          </div>
        </section>
        {LATEST_END}"""
    )


def replace_latest_block(landing_text: str, new_block: str) -> str:
    pattern = re.compile(
        re.escape(LATEST_START) + r".*?" + re.escape(LATEST_END),
        flags=re.DOTALL,
    )
    updated, count = pattern.subn(new_block, landing_text)
    if count != 1:
        raise NewsError("The Latest news block could not be replaced safely.")
    return updated


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def run_strict_build() -> bool:
    print("\nRunning strict Sphinx build...\n")
    command = [
        sys.executable,
        "-m",
        "sphinx",
        "-W",
        "--keep-going",
        "-E",
        "-a",
        "-b",
        "html",
        "docs",
        str(BUILD_DIRECTORY.relative_to(PROJECT_ROOT)),
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT).returncode == 0


def open_local_preview() -> bool:
    preview = BUILD_DIRECTORY / "index.html"
    if sys.platform == "darwin" and shutil.which("open"):
        result = subprocess.run(["open", str(preview)], cwd=PROJECT_ROOT)
        return result.returncode == 0
    return False


def preserve_failed_draft(target: Path, draft_path: Optional[Path]) -> Optional[Path]:
    if draft_path and draft_path.exists():
        return draft_path
    if not target.exists():
        return None
    DRAFT_DIRECTORY.mkdir(exist_ok=True)
    recovery_path = DRAFT_DIRECTORY / target.name
    if recovery_path.exists():
        recovery_path = DRAFT_DIRECTORY / (target.stem + "-recovered.md")
    shutil.move(str(target), recovery_path)
    return recovery_path


def cleanup_successful_draft(draft_path: Optional[Path]) -> None:
    if draft_path:
        draft_path.unlink(missing_ok=True)
    if DRAFT_DIRECTORY.exists() and not any(DRAFT_DIRECTORY.iterdir()):
        DRAFT_DIRECTORY.rmdir()


def main() -> int:
    args = parse_arguments()
    print("=========================================================")
    print("          AQ PORTAL - CREATE A NEWS ITEM")
    print("=========================================================")
    print("This changes local files only. It does not commit or publish.\n")

    landing_original, news_index_original = verify_project()
    publication_date = prompt_date(args.date)
    title = prompt_required("News title", args.title)
    summary = prompt_required("Short landing-page summary", args.summary)
    source = prompt_source(args.source)

    slug = slugify(title)
    stem = f"{publication_date.isoformat()}-{slug}"
    filename = stem + ".md"
    target = NEWS_DIRECTORY / filename
    if target.exists():
        raise NewsError(f"A news file with this name already exists:\n  {target}")

    prefix = article_prefix(title, publication_date, source)
    article_text, draft_path = obtain_article_body(args, filename, prefix)
    updated_news_index = insert_news_entry(news_index_original, stem, publication_date)
    latest_block = build_latest_block(stem, title, summary, publication_date)
    updated_landing = replace_latest_block(landing_original, latest_block)

    print("\nProposed news item")
    print("---------------------------------------------------------")
    print(f"Date    : {publication_date.isoformat()}")
    print(f"Title   : {title}")
    print(f"Summary : {summary}")
    print(f"File    : docs/news/{filename}")

    if not args.yes:
        answer = input("\nCreate the news item and run the build? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("News creation cancelled. The draft has been preserved.")
            if draft_path:
                print(f"Draft: {draft_path}")
            return 0

    wrote_files = False
    try:
        wrote_files = True
        atomic_write(target, article_text)
        atomic_write(NEWS_INDEX, updated_news_index)
        atomic_write(LANDING_PAGE, updated_landing)

        if not run_strict_build():
            raise NewsError("The strict Sphinx build failed.")
    except Exception:
        if wrote_files:
            atomic_write(NEWS_INDEX, news_index_original)
            atomic_write(LANDING_PAGE, landing_original)
            recovery = preserve_failed_draft(target, draft_path)
            if target.exists():
                target.unlink()
            print("\nThe navigation and landing page were restored.")
            if recovery:
                print(f"Your article was preserved as a draft:\n  {recovery}")
        raise

    cleanup_successful_draft(draft_path)
    preview_opened = open_local_preview()
    print("\n=========================================================")
    print("✓ NEWS ITEM CREATED AND STRICT BUILD COMPLETED")
    print("=========================================================")
    print(f"Article    : docs/news/{filename}")
    print("News index : docs/news/index.md")
    print("Landing    : docs/index.md")
    if preview_opened:
        print("Preview    : opened in your browser")
    else:
        print("Preview    : build/html/index.html")
    print("\nNothing has been committed or published.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nNews creation cancelled.")
        raise SystemExit(130)
    except NewsError as error:
        print(f"\n❌ {error}")
        raise SystemExit(1)
    except subprocess.CalledProcessError as error:
        print(f"\n❌ The editor command failed: {error}")
        raise SystemExit(1)
