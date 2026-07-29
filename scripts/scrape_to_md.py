#!/usr/bin/env python3
"""Scrape the European Air Quality Portal (WordPress) into Sphinx-ready Markdown.

Content is pulled from two places:

* the WordPress REST API, for the canonical list of pages/posts and their
  metadata (title, slug, date, category);
* the rendered public HTML of each page, because the portal is built with
  Elementor and several widgets (PDF viewers, Tableau dashboards) are only
  expanded when the page is actually rendered.

Embedded viewers (``<iframe>``, ``<tableau-viz>``, Tableau ``<object>``) cannot
survive the trip to static Markdown, so each one is replaced by a link. A small
JS snippet shipped with the docs makes every external link open in a new tab.

Usage::

    python scripts/scrape_to_md.py [--out docs] [--cache .cache] [--offline]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

SITE = "https://aqportal.discomap.eea.europa.eu"

# The production site's content still contains absolute links to the staging
# host. Both are treated as "this site" so internal links resolve locally.
INTERNAL_HOSTS = {
    "aqportal.discomap.eea.europa.eu",
    "eeadmz1-cws-wp-air02-dev.azurewebsites.net",
}

USER_AGENT = "aqportal-docs-export/1.0 (+https://github.com/)"
REQUEST_DELAY = 0.2

# Elementor widgets that carry no meaning once styling and JavaScript are
# gone. The countdown is a live timer to the next submission deadline; it
# renders as "Days Hours Minutes Seconds Game over!" without its script, and
# the deadline date is stated in the paragraph above it anyway.
NOISE_WIDGETS = {"spacer.default", "divider.default", "countdown.default"}


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------


class Fetcher:
    """Fetches URLs, caching every response on disk."""

    def __init__(self, cache_dir: Path, offline: bool = False):
        self.cache_dir = cache_dir
        self.offline = offline
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, url: str, suffix: str) -> Path:
        key = re.sub(r"[^A-Za-z0-9._-]+", "_", url)[:180]
        return self.cache_dir / f"{key}{suffix}"

    def get(self, url: str, suffix: str = ".dat") -> bytes:
        path = self._cache_path(url, suffix)
        if path.exists():
            return path.read_bytes()
        if self.offline:
            raise RuntimeError(f"offline mode and {url} is not cached")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        path.write_bytes(data)
        time.sleep(REQUEST_DELAY)
        return data

    def get_text(self, url: str, suffix: str = ".html") -> str:
        return self.get(url, suffix).decode("utf-8", errors="replace")

    def get_json(self, url: str):
        return json.loads(self.get_text(url, ".json"))


def fetch_collection(fetcher: Fetcher, kind: str) -> list[dict]:
    """Fetch every item of a WordPress REST collection, following pagination."""
    items: list[dict] = []
    page = 1
    while True:
        url = f"{SITE}/wp-json/wp/v2/{kind}?per_page=100&page={page}"
        batch = fetcher.get_json(url)
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


# --------------------------------------------------------------------------
# Document model
# --------------------------------------------------------------------------


@dataclass
class Doc:
    """One WordPress page or post, and where it lands in the Sphinx tree."""

    wp_id: int
    kind: str  # "page" or "post"
    slug: str
    title: str
    url: str
    date: str
    modified: str
    categories: list[str] = field(default_factory=list)
    body: str = ""

    @property
    def docname(self) -> str:
        """Sphinx docname, e.g. ``pages/toolbox``."""
        folder = "pages" if self.kind == "page" else "news"
        stem = self.slug if self.kind == "page" else f"{self.date[:10]}-{self.slug}"
        return f"{folder}/{stem}"

    @property
    def path_parts(self) -> tuple[str, str]:
        folder, _, stem = self.docname.partition("/")
        return folder, stem + ".md"


def unescape_title(raw: str) -> str:
    """WordPress titles arrive as HTML; flatten them to plain text."""
    text = BeautifulSoup(raw, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


# --------------------------------------------------------------------------
# Link handling
# --------------------------------------------------------------------------


def split_url(url: str) -> tuple[str, str, str]:
    parsed = urllib.parse.urlsplit(url)
    return parsed.netloc, parsed.path, parsed.fragment


def is_internal(url: str) -> bool:
    netloc, _, _ = split_url(url)
    return netloc in INTERNAL_HOSTS or (netloc == "" and not url.startswith("#"))


class LinkResolver:
    """Maps site URLs onto Sphinx docnames."""

    def __init__(self, docs: list[Doc]):
        self.by_path: dict[str, Doc] = {}
        for doc in docs:
            _, path, _ = split_url(doc.url)
            self.by_path[path.rstrip("/") or "/"] = doc
        # The portal's front page is the "welcome" page.
        welcome = next((d for d in docs if d.slug == "welcome-to-the-aq-portal"), None)
        if welcome:
            self.by_path["/"] = welcome
        # /news/ is an empty landing page upstream; point it at the news index
        # so the link lands somewhere that actually lists the news items.
        self.news_index = "news/index"

    def resolve(self, url: str, current: Doc) -> str | None:
        """Return a relative Markdown target, or None if the link stays external."""
        if not is_internal(url):
            return None
        netloc, path, fragment = split_url(url)
        key = path.rstrip("/") or "/"
        if key == "/news":
            rel = relative_docname(current.docname, self.news_index)
            return rel + (f"#{fragment}" if fragment else "")
        target = self.by_path.get(key)
        if target is None:
            # Unknown internal path (uploads, plugin endpoints): absolutise it
            # so the link keeps working from the generated docs.
            if netloc == "":
                return SITE + url if url.startswith("/") else None
            return None
        rel = relative_docname(current.docname, target.docname)
        return rel + (f"#{fragment}" if fragment else "")


def relative_docname(source: str, target: str) -> str:
    """Relative .md path from one docname to another."""
    src_dir = source.rsplit("/", 1)[0] if "/" in source else ""
    tgt_dir, _, tgt_name = target.rpartition("/")
    if src_dir == tgt_dir:
        return f"{tgt_name}.md"
    prefix = "../" * (len(src_dir.split("/")) if src_dir else 0)
    return f"{prefix}{target}.md"


# --------------------------------------------------------------------------
# HTML preprocessing
# --------------------------------------------------------------------------


# Tried in order; the portal mixes Elementor-built pages with classic theme
# posts, and the classic ones must not fall through to <main>, which also
# holds the page header, breadcrumbs and post thumbnail.
CONTENT_SELECTORS = (
    'div[data-elementor-type="wp-page"]',
    'div[data-elementor-type="wp-post"]',
    "main#main .entry-content",
    "article .entry-content",
    ".entry-content",
)


def extract_content(html: str) -> BeautifulSoup | None:
    """Pull the article body out of a full portal page."""
    soup = BeautifulSoup(html, "lxml")
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is not None:
            return node
    return None


def make_link_paragraph(soup: BeautifulSoup, label: str, href: str, note: str) -> BeautifulSoup:
    """Build the replacement block used for every embedded viewer."""
    wrapper = soup.new_tag("div")

    para = soup.new_tag("p")
    em = soup.new_tag("em")
    em.string = note
    para.append(em)
    wrapper.append(para)

    link_para = soup.new_tag("p")
    anchor = soup.new_tag("a", href=href)
    anchor.string = label
    link_para.append(anchor)
    wrapper.append(link_para)
    return wrapper


def pdf_target(src: str) -> str:
    """Recover the real PDF URL from a pdfjs-viewer-shortcode iframe src."""
    query = urllib.parse.urlsplit(src).query
    params = urllib.parse.parse_qs(query)
    target = (params.get("file") or [""])[0]
    if not target:
        return src
    if target.startswith("/"):
        target = SITE + target
    return target


def tableau_label(url: str) -> str:
    """Name a Tableau view as ``workbook / view``.

    Several dashboards share a view name ("General", "Master"), so the view
    alone is not enough to tell them apart in a list of links.
    """
    path = urllib.parse.urlsplit(url).path.strip("/")
    parts = [p for p in path.split("/") if p and p != "views"]
    if len(parts) >= 2:
        return f"{parts[-2]} / {parts[-1]}"
    return parts[-1] if parts else "dashboard"


def tableau_object_url(node) -> str | None:
    """Rebuild the view URL from a legacy Tableau <object> embed."""
    params = {p.get("name"): (p.get("value") or "") for p in node.find_all("param")}
    host = urllib.parse.unquote(params.get("host_url", "")).rstrip("/")
    name = params.get("name", "")
    if not host or not name:
        return None
    return f"{host}/views/{name.replace('/', '/')}"


def convert_embeds(node: BeautifulSoup, doc: Doc, report: list[str]) -> None:
    """Replace every embedded viewer with a plain link."""
    soup = node if isinstance(node, BeautifulSoup) else BeautifulSoup("", "lxml")

    for frame in node.find_all("iframe"):
        src = frame.get("src") or ""
        if not src:
            frame.decompose()
            continue
        if "pdfjs-viewer-shortcode" in src:
            href = pdf_target(src)
            label = href.rsplit("/", 1)[-1] or "Open PDF"
            frame.replace_with(
                make_link_paragraph(
                    soup, f"Open the PDF: {label}", href,
                    "This document is embedded in a PDF viewer on the original site.",
                )
            )
            report.append(f"{doc.docname}: pdf iframe -> {href}")
        else:
            title = frame.get("title") or "Open the embedded content"
            href = src if "://" in src else urllib.parse.urljoin(SITE, src)
            frame.replace_with(
                make_link_paragraph(
                    soup, title, href,
                    "This content is embedded in a frame on the original site.",
                )
            )
            report.append(f"{doc.docname}: iframe -> {href}")

    for viz in node.find_all("tableau-viz"):
        href = viz.get("src") or ""
        label = tableau_label(href) if href else "dashboard"
        viz.replace_with(
            make_link_paragraph(
                soup, f"Open the interactive dashboard: {label}", href,
                "This Tableau dashboard is embedded on the original site.",
            )
        )
        report.append(f"{doc.docname}: tableau-viz -> {href}")

    for obj in node.find_all("object", class_="tableauViz"):
        href = tableau_object_url(obj)
        if not href:
            obj.decompose()
            continue
        label = tableau_label(href)
        obj.replace_with(
            make_link_paragraph(
                soup, f"Open the interactive dashboard: {label}", href,
                "This Tableau dashboard is embedded on the original site.",
            )
        )
        report.append(f"{doc.docname}: tableau object -> {href}")

    # The Tableau/PDF loader scripts are meaningless in static docs.
    for tag in node.find_all(["script", "style", "noscript"]):
        tag.decompose()


def convert_widgets(node: BeautifulSoup) -> None:
    """Flatten the Elementor widgets that carry content into plain HTML."""
    soup = node if isinstance(node, BeautifulSoup) else BeautifulSoup("", "lxml")

    for widget in node.select("[data-widget_type]"):
        if widget.get("data-widget_type") in NOISE_WIDGETS:
            widget.decompose()

    # Flip boxes: a picture and title on the front, a description and link on
    # the back. Rendered as a heading + description + link.
    for box in node.select('[data-widget_type="flip-box.default"]'):
        title_el = box.select_one(".elementor-flip-box__layer__title")
        desc_el = box.select_one(".elementor-flip-box__layer__description")
        image_el = box.select_one(".elementor-flip-box__image img")
        back = box.select_one("a.elementor-flip-box__back")
        href = back.get("href") if back else None

        block = soup.new_tag("div")
        if image_el is not None:
            figure = soup.new_tag("p")
            # The illustration is decorative on the portal; give it the box's
            # own title as alt text so it is not announced as unlabelled.
            image_el.attrs["alt"] = image_el.get("alt") or (
                title_el.get_text(" ", strip=True) if title_el else ""
            )
            figure.append(image_el.extract())
            block.append(figure)
        heading = soup.new_tag("h3")
        title_text = title_el.get_text(" ", strip=True) if title_el else "Untitled"
        if href:
            anchor = soup.new_tag("a", href=href)
            anchor.string = title_text
            heading.append(anchor)
        else:
            heading.string = title_text
        block.append(heading)
        if desc_el:
            para = soup.new_tag("p")
            para.string = desc_el.get_text(" ", strip=True)
            block.append(para)
        box.replace_with(block)

    # Buttons are just links with heavy styling.
    for button in node.select('[data-widget_type="button.default"]'):
        anchor = button.select_one("a")
        if anchor is None:
            button.decompose()
            continue
        text = anchor.get_text(" ", strip=True) or anchor.get("href", "link")
        new_anchor = soup.new_tag("a", href=anchor.get("href", ""))
        new_anchor.string = text
        para = soup.new_tag("p")
        para.append(new_anchor)
        button.replace_with(para)

    # Controls injected by the PDF viewer plugin ("Skip to PDF content",
    # "View Fullscreen"). They drive the embedded viewer, which the export
    # replaces with a direct link to the PDF, so they have nothing left to do.
    for anchor in node.find_all("a", href=re.compile(r"#pdfjs-viewer-skip|pdfjs-viewer-shortcode")):
        anchor.decompose()


def download_images(node: BeautifulSoup, fetcher: Fetcher, images_dir: Path,
                    doc: Doc, report: list[str]) -> None:
    """Save every content image next to the docs and rewrite its src."""
    images_dir.mkdir(parents=True, exist_ok=True)
    depth = doc.docname.count("/")
    prefix = "../" * depth

    for img in node.find_all("img"):
        src = img.get("data-src") or img.get("src") or ""
        img.attrs.pop("srcset", None)
        img.attrs.pop("sizes", None)
        if not src or src.startswith("data:"):
            img.decompose()
            continue
        absolute = src if "://" in src else urllib.parse.urljoin(SITE, src)
        name = urllib.parse.unquote(urllib.parse.urlsplit(absolute).path.rsplit("/", 1)[-1])
        name = re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "image.png"
        try:
            data = fetcher.get(absolute, "." + name)
        except Exception as exc:  # noqa: BLE001 - a missing image must not stop the run
            report.append(f"{doc.docname}: image download failed {absolute} ({exc})")
            img.attrs["src"] = absolute
            continue
        (images_dir / name).write_bytes(data)
        img.attrs = {"src": f"{prefix}_static/images/{name}", "alt": img.get("alt", "")}


def rewrite_links(node: BeautifulSoup, resolver: LinkResolver, doc: Doc,
                  report: list[str]) -> None:
    for anchor in node.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue
        resolved = resolver.resolve(href, doc)
        if resolved:
            anchor["href"] = resolved
        elif split_url(href)[0] == "":
            anchor["href"] = urllib.parse.urljoin(SITE, href)


EMPHASIS_GROUPS = ({"em", "i"}, {"b", "strong"})


def flatten_nested_emphasis(node: BeautifulSoup) -> None:
    """Unwrap emphasis nested inside the same kind of emphasis.

    Some pages were pasted in from email clients and carry markup such as
    ``<em>...<i>...</i></em>``. Both map to ``*`` in Markdown, so the nesting
    emits a stray ``**`` that renders literally. HTML collapses the duplicate
    silently; Markdown does not.
    """
    for group in EMPHASIS_GROUPS:
        for tag in node.find_all(list(group)):
            if any(parent.name in group for parent in tag.parents):
                tag.unwrap()


def strip_empty(node: BeautifulSoup) -> None:
    """Drop the Elementor layout divs that hold nothing but whitespace."""
    for _ in range(6):
        removed = False
        for tag in node.find_all(["div", "section", "span", "p", "u", "b", "strong", "em"]):
            if tag.find(["img", "a", "table", "hr", "br", "iframe"]):
                continue
            if not tag.get_text(strip=True):
                tag.decompose()
                removed = True
        if not removed:
            break


# --------------------------------------------------------------------------
# Markdown conversion
# --------------------------------------------------------------------------


class PortalConverter(MarkdownConverter):
    """Markdownify tuned for MyST output."""

    def convert_u(self, el, text, parent_tags=None):
        # The portal underlines text for emphasis; underline has no Markdown
        # equivalent, and bold/italics would double up on nested markup.
        return text

    def convert_img(self, el, text, parent_tags=None):
        src = el.get("src", "")
        alt = el.get("alt", "") or ""
        return f"![{alt}]({src})"


def to_markdown(node) -> str:
    converter = PortalConverter(
        heading_style="ATX",
        bullets="-",
        strip=["script", "style", "noscript", "param", "object"],
        escape_underscores=False,
        escape_asterisks=False,
    )
    md = converter.convert_soup(node)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    md = re.sub(r"\xa0", " ", md)
    return md.strip()


HEADING_RE = re.compile(r"^(#{1,6}) (?=\S)", re.MULTILINE)


def normalise_headings(md: str) -> str:
    """Shift the body's headings so they sit directly under the page title.

    The page title is the document's only H1, and Sphinx warns about skipped
    levels, so the shallowest heading in the body becomes H2 and the rest move
    with it.
    """
    levels = [len(m.group(1)) for m in HEADING_RE.finditer(md)]
    if not levels:
        return md
    shift = 2 - min(levels)
    if shift == 0:
        return md
    return HEADING_RE.sub(
        lambda m: "#" * max(2, min(6, len(m.group(1)) + shift)) + " ", md
    )


EMPTY_NOTICE = """```{{note}}
This page carries no content of its own on the portal — it exists as a heading
in the site navigation. See the [live page]({url}) for the current state.
```"""


def render_page(doc: Doc) -> str:
    lines = [f"# {doc.title}", ""]
    meta = [f"*Source: [{doc.url}]({doc.url})*"]
    if doc.kind == "post":
        meta.insert(0, f"*Published: {doc.date[:10]}*")
    lines.append("  \n".join(meta))
    lines.extend(["", doc.body, ""])
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Index generation
# --------------------------------------------------------------------------

# Order follows the portal's own top navigation; anything not listed is
# appended alphabetically so new pages still show up.
VIEWERS_SECTION = "Viewers and dashboards"
REFERENCE_SECTION = "Reference"

# The sidebar. The seven pages under "Viewers and dashboards" are the ones the
# portal's own catalogue groups its applications under, so each carries the
# gallery for its group (scripts/build_gallery.py); "AQ eReporting" is the
# eighth such page but reads as an introduction, so it sits in Getting started.
SECTIONS: list[tuple[str, list[str]]] = [
    ("Getting started", [
        "welcome-to-the-aq-portal",
        "aq-ereporting",
        "reporting-year-overview",
        "how-to-use-the-viewers",
        "reporters-package",
    ]),
    (VIEWERS_SECTION, [
        "data-flows-monitors",
        "data-tables",
        "air-quality-now",
        "data-analysis-and-stats",
        "focus-on-cities",
        "compliance-status",
        "impact-on-health",
        "direct-access-to-viewers-and-tablesviewers-direct-access",
    ]),
    ("Data and downloads", [
        "download-data",
    ]),
    (REFERENCE_SECTION, [
        "toolbox",
        "aq-insights",
        "legal-aspects",
        "meetings",
        "links",
    ]),
]

# Scratch pages left in the CMS (a stray PDF embed and one loose sentence).
# Pass --include-drafts to export them anyway.
DRAFT_SLUGS = {"test", "testing"}

# The portal's own News page is an empty navigation heading; news/index.md
# takes its place and lists the actual posts.
REPLACED_BY_INDEX = {"news"}


SYNC_DUPLICATE_RE = re.compile(r" \d+(\.[^.]+)$")


def purge_sync_duplicates(out: Path) -> list[str]:
    """Delete the "name 2.md" copies a file-sync client leaves behind.

    This project is typically checked out under a synced folder (iCloud Drive,
    OneDrive, Dropbox). Each run deletes and rewrites the whole of pages/ and
    news/, which races with the sync client and leaves stale numbered copies.
    Sphinx then treats every copy as a real document and the -W build fails on
    "document isn't included in any toctree".

    Only files whose un-numbered original was just written are removed, so a
    genuine file that happens to end in a number is never touched.
    """
    removed = []
    for folder in ("pages", "news"):
        target = out / folder
        if not target.is_dir():
            continue
        for path in target.iterdir():
            if not SYNC_DUPLICATE_RE.search(path.name):
                continue
            original = path.with_name(SYNC_DUPLICATE_RE.sub(r"\1", path.name))
            if original.exists():
                path.unlink()
                removed.append(f"{folder}/{path.name}")
    return removed


def toctree(caption: str, entries: list[str], maxdepth: int = 1) -> str:
    body = "\n".join(entries)
    return (f"```{{toctree}}\n:maxdepth: {maxdepth}\n:caption: {caption}\n\n"
            f"{body}\n```\n")


def write_indexes(out: Path, pages: list[Doc], posts: list[Doc]) -> None:
    """Write the news index and the sectioned root toctree.

    The portal itself is flat — every page is a direct child of the front page
    — so the sidebar follows the grouping the portal uses in its own catalogue
    of viewers (see SECTIONS) rather than a hierarchy scraped from the site.
    """
    posts = sorted(posts, key=lambda d: d.date, reverse=True)
    have = {d.slug for d in pages}

    news_lines = ["# News", "", "News items published on the portal, most recent first.", ""]
    news_lines += ["```{toctree}", ":maxdepth: 1", ""]
    news_lines += [d.path_parts[1][:-3] for d in posts]
    news_lines += ["```", ""]
    (out / "news" / "index.md").write_text("\n".join(news_lines), encoding="utf-8")

    # A page listed in no section would be an orphan and fail the -W build,
    # so anything new upstream is swept into Reference.
    placed = {slug for _, slugs in SECTIONS for slug in slugs if slug in have}
    leftovers = sorted(have - placed)

    blocks = []
    for caption, slugs in SECTIONS:
        entries = [f"pages/{s}" for s in slugs if s in have]
        if caption == VIEWERS_SECTION:
            entries.insert(0, "viewers/index")
        if caption == REFERENCE_SECTION:
            entries += [f"pages/{s}" for s in leftovers]
        if entries:
            blocks.append(toctree(caption, entries))
    blocks.append(toctree("News", ["news/index"]))

    (out / "index.md").write_text(
        "# European Air Quality Portal\n\n"
        "A Markdown export of the [European Air Quality Portal]"
        f"({SITE}), the data and information gateway on air quality in Europe, "
        "rendered as documentation with Sphinx.\n\n"
        "Start with [Welcome to the AQ Portal](pages/welcome-to-the-aq-portal.md) "
        "for what the portal is, or go straight to the "
        "[viewers and dashboards](viewers/index.md) for the interactive "
        "applications.\n\n"
        "Interactive dashboards and embedded PDF viewers cannot be reproduced in "
        "static documentation; wherever the original page embedded one, this "
        "export links to it instead. Links to other sites open in a new tab.\n\n"
        + "\n".join(blocks) +
        "\n## Indices\n\n- {ref}`genindex`\n- {ref}`search`\n",
        encoding="utf-8",
    )
    if leftovers:
        print(f"  note: {', '.join(leftovers)} not in SECTIONS; filed under Reference")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def build(out: Path, cache: Path, offline: bool, include_drafts: bool) -> int:
    fetcher = Fetcher(cache, offline=offline)

    print("Fetching the page and post lists from the WordPress REST API...")
    raw_pages = fetch_collection(fetcher, "pages")
    raw_posts = fetch_collection(fetcher, "posts")
    categories = {c["id"]: c["name"] for c in fetch_collection(fetcher, "categories")}

    docs: list[Doc] = []
    skipped: list[str] = []
    for item in raw_pages:
        if item["slug"] in DRAFT_SLUGS and not include_drafts:
            skipped.append(f"{item['slug']} (scratch page; --include-drafts to export)")
            continue
        if item["slug"] in REPLACED_BY_INDEX:
            skipped.append(f"{item['slug']} (empty upstream; replaced by news/index)")
            continue
        docs.append(Doc(
            wp_id=item["id"], kind="page", slug=item["slug"],
            title=unescape_title(item["title"]["rendered"]),
            url=item["link"], date=item["date"], modified=item["modified"],
        ))
    for item in raw_posts:
        docs.append(Doc(
            wp_id=item["id"], kind="post", slug=item["slug"],
            title=unescape_title(item["title"]["rendered"]),
            url=item["link"], date=item["date"], modified=item["modified"],
            categories=[categories.get(c, str(c)) for c in item.get("categories", [])],
        ))

    resolver = LinkResolver(docs)
    report: list[str] = []
    images_dir = out / "_static" / "images"

    for folder in ("pages", "news"):
        target = out / folder
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)

    print(f"Converting {len(docs)} documents...")
    for doc in docs:
        html = fetcher.get_text(doc.url)
        node = extract_content(html)
        if node is None:
            report.append(f"{doc.docname}: no content container found")
            doc.body = EMPTY_NOTICE.format(url=doc.url)
        else:
            convert_embeds(node, doc, report)
            convert_widgets(node)
            download_images(node, fetcher, images_dir, doc, report)
            rewrite_links(node, resolver, doc, report)
            flatten_nested_emphasis(node)
            strip_empty(node)
            doc.body = normalise_headings(to_markdown(node))
            if not doc.body.strip():
                doc.body = EMPTY_NOTICE.format(url=doc.url)
                report.append(f"{doc.docname}: empty on the portal itself")

        folder, filename = doc.path_parts
        (out / folder / filename).write_text(render_page(doc), encoding="utf-8")

    write_indexes(out, [d for d in docs if d.kind == "page"],
                  [d for d in docs if d.kind == "post"])

    duplicates = purge_sync_duplicates(out)
    if duplicates:
        print(f"\nRemoved {len(duplicates)} file-sync duplicate(s) "
              f"(e.g. {duplicates[0]})")

    print(f"\nWrote {len(docs)} Markdown files to {out}/")
    if skipped:
        print("\nSkipped:")
        for line in skipped:
            print(f"  - {line}")
    if report:
        print("\nConversion notes:")
        for line in report:
            print(f"  - {line}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("docs"))
    parser.add_argument("--cache", type=Path, default=Path(".cache"))
    parser.add_argument("--offline", action="store_true",
                        help="use only the on-disk cache; never hit the network")
    parser.add_argument("--include-drafts", action="store_true",
                        help="also export the CMS scratch pages (test, testing)")
    args = parser.parse_args()
    return build(args.out.resolve(), args.cache.resolve(), args.offline,
                 args.include_drafts)


if __name__ == "__main__":
    sys.exit(main())
