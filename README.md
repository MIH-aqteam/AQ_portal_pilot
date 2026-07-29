# European Air Quality Portal — Markdown / Sphinx export

A Markdown export of the [European Air Quality Portal](https://aqportal.discomap.eea.europa.eu/),
built into a documentation site with [Sphinx](https://www.sphinx-doc.org/) and
publishable to GitHub Pages.

The export covers **19 content pages** and **36 news posts**.

## Layout

```
docs/                     Sphinx project
  conf.py                 build configuration
  index.md                landing page and root toctree
  pages/                  the portal's content pages
  news/                   news posts, one file per post
  _static/
    external-links.js     makes off-site links open in a new tab
    images/               images pulled from the portal
scripts/
  scrape_to_md.py         the exporter
requirements.txt
.github/workflows/docs.yml
```

## Building

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Re-export from the live portal (cached in .cache/, safe to re-run)
.venv/bin/python scripts/scrape_to_md.py

# Build the HTML
.venv/bin/python -m sphinx -b html docs docs/_build/html
open docs/_build/html/index.html
```

The generated Markdown is committed, so building the site does not require
network access — only re-exporting does.

### Exporter options

| Flag | Effect |
| --- | --- |
| `--out DIR` | Where to write the Markdown (default `docs`) |
| `--cache DIR` | Where to cache HTTP responses (default `.cache`) |
| `--offline` | Use only the cache; never hit the network |
| `--include-drafts` | Also export the CMS scratch pages `test` and `testing` |

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

## Licence

The exported content belongs to the European Environment Agency; see the
[portal's legal notice](https://aqportal.discomap.eea.europa.eu/legal-aspects/).
The exporter script is provided as-is.
