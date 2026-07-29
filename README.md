# European Air Quality Portal — Markdown / Sphinx export

A Markdown export of the [European Air Quality Portal](https://aqportal.discomap.eea.europa.eu/),
built into a documentation site with [Sphinx](https://www.sphinx-doc.org/) and
publishable to GitHub Pages.

The export covers **19 content pages**, **36 news posts**, and a visual
catalogue of the **51 viewers and dashboards** the portal links to.

## Layout

```
docs/                     Sphinx project
  conf.py                 build configuration
  index.md                landing page and the sectioned root toctree
  pages/                  the portal's content pages
  news/                   news posts, one file per post
  viewers/index.md        generated gallery of all 51 applications
  _data/applications.json generated catalogue (id, group, name, url)
  _static/
    external-links.js     makes off-site links open in a new tab
    custom.css            table and gallery styling
    images/               images pulled from the portal
    thumbnails/           one screenshot per application
scripts/
  scrape_to_md.py         the exporter
  capture_thumbnails.py   screenshots every application (bulk)
  capture_cdp.py          screenshots the map viewers the bulk path can't
  build_gallery.py        builds the gallery page and the per-page galleries
requirements.txt
.github/workflows/docs.yml
```

## Building

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Build the HTML from the committed Markdown
.venv/bin/python -m sphinx -b html docs docs/_build/html
open docs/_build/html/index.html
```

The generated Markdown and thumbnails are committed, so building the site needs
no network access — only refreshing the content does.

### Refreshing the content

Run these in order; `build_gallery.py` must come last, because `scrape_to_md.py`
rewrites the pages that the galleries are injected into.

```bash
.venv/bin/python scripts/scrape_to_md.py        # re-export from the portal
.venv/bin/python scripts/capture_thumbnails.py  # re-screenshot the applications
.venv/bin/python scripts/build_gallery.py       # rebuild the galleries
```

### Exporter options

| Flag | Effect |
| --- | --- |
| `--out DIR` | Where to write the Markdown (default `docs`) |
| `--cache DIR` | Where to cache HTTP responses (default `.cache`) |
| `--offline` | Use only the cache; never hit the network |
| `--include-drafts` | Also export the CMS scratch pages `test` and `testing` |

## Navigation

The portal is flat — every page is a direct child of its front page, and its
menu has no sub-levels. The sidebar here therefore follows the grouping the
portal uses in its *own* catalogue of viewers (the "Box" column of the
"Direct access to viewers and tables" table), rather than a hierarchy scraped
from the site:

| Section | Contents |
| --- | --- |
| Getting started | Welcome, AQ eReporting, Reporting year overview, How to use the viewers, Reporter's package |
| Viewers and dashboards | The gallery, plus the seven pages that describe a group of applications, plus the full catalogue table |
| Data and downloads | Download data |
| Reference | Toolbox, AQ Insights, Legal aspects, Meetings, Links |
| News | 36 posts, newest first |

The section list lives in `SECTIONS` in `scripts/scrape_to_md.py`. A page that
appears upstream but is listed in no section is swept into Reference, so a new
page can never silently become an orphan and break the `-W` build.

## Thumbnails

`capture_thumbnails.py` renders each application in headless Chrome and
downscales it with `sips` (macOS). Two things it handles that are worth knowing:

- **Map viewers need software WebGL.** The ArcGIS attainment viewer, the Air
  Quality Index map and the modelling viewer draw into a WebGL canvas that
  `--disable-gpu` leaves blank. Those are captured by `capture_cdp.py --webgl`,
  which drives Chrome over the DevTools Protocol and waits real seconds —
  Chrome's `--virtual-time-budget` never expires on pages that keep a timer
  running forever, so the normal path hangs on them instead.
- **Blank captures are reported, not shipped.** Anything that renders as a flat
  colour is flagged so it can be checked rather than published as an empty
  frame.

49 of the 51 applications have a thumbnail. The two without are covered under
"Notes on the source site" below.

## How the export works

Content comes from two sources:

- the **WordPress REST API** (`/wp-json/wp/v2/`) for the canonical list of pages
  and posts plus their metadata;
- the **rendered public HTML** of each page, because the portal is built with
  Elementor and some widgets (PDF viewers, Tableau dashboards) only appear once
  the page is actually rendered.

The exporter then strips Elementor's layout scaffolding, flattens its widgets
(flip boxes become a heading + description + link, buttons become links),
rewrites internal links to point at the corresponding Markdown file, downloads
images into `docs/_static/images/`, and converts what remains to Markdown.

### Embedded viewers become links

Interactive embeds cannot survive the trip to static Markdown, so each one is
replaced by a short note and a link:

| Embed on the portal | In the docs |
| --- | --- |
| `<tableau-viz>` and Tableau `<object>` dashboards | link to the Tableau view |
| PDF.js viewer `<iframe>` | link to the underlying PDF |
| any other `<iframe>` | link to the frame's source |

`docs/_static/external-links.js` adds `target="_blank"` and
`rel="noopener noreferrer"` to every link that leaves the documentation, so
these open in a new browser tab.

## Deploying to GitHub Pages

`.github/workflows/docs.yml` builds the docs on every push to `main` and
deploys them. In the repository, set **Settings → Pages → Source** to
**GitHub Actions**. The build runs with `-W`, so any Sphinx warning fails it.

## Notes on the source site

Things worth knowing about the portal, found while exporting it:

- **Four navigation pages are empty upstream.** `Toolbox`, `Legal aspects`,
  `Meetings` and `News` render no content on the live site — they exist only as
  headings in the menu. The first three are exported as stubs carrying a note;
  `News` is replaced by `docs/news/index.md`, which lists the actual posts.
- **The site is flat.** Every page is a direct child of the front page, so the
  toctree in `docs/pages/index.md` uses a hand-kept reading order
  (`NAV_ORDER` in the exporter) rather than a hierarchy scraped from the site.
- **Production content links to the staging host.** Several links in the live
  pages point at `eeadmz1-cws-wp-air02-dev.azurewebsites.net`. The exporter
  treats that host as internal so those links resolve correctly here, but they
  are a bug on the portal itself.
- **`test` and `testing` are scratch pages** left in the CMS. They are skipped
  unless you pass `--include-drafts`.
- **Two linked applications are gone.** Rows 42 and 43 of the catalogue —
  "E1a (from 2013)" and "E2a (current year)", both already marked discontinued —
  return HTTP 404. They appear in the gallery as "Not available" rather than
  being quietly dropped. Every other application answered 200 when this export
  was generated.

## A note on file sync

This project is usually checked out under `~/Documents`, which iCloud Drive
syncs. Because the exporter deletes and rewrites all of `docs/pages` and
`docs/news` on each run, the sync client races with it and leaves behind
byte-identical `name 2.md` copies. Sphinx treats each copy as a real document
and the `-W` build then fails on "document isn't included in any toctree".

`scrape_to_md.py` deletes those copies at the end of every run, and
`.gitignore` refuses them as a second line of defence. The real fix is to keep
the project outside a synced folder.

## Licence

The exported content belongs to the European Environment Agency; see the
[portal's legal notice](https://aqportal.discomap.eea.europa.eu/legal-aspects/).
The exporter script is provided as-is.
