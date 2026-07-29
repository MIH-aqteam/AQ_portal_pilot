"""Sphinx configuration for the European Air Quality Portal documentation export."""

project = "European Air Quality Portal"
author = "European Environment Agency"
copyright = "European Environment Agency — content exported from aqportal.discomap.eea.europa.eu"
release = "1.0"

extensions = [
    "myst_parser",
    "sphinx.ext.githubpages",  # emits .nojekyll so GitHub Pages serves _static/
]

source_suffix = {".md": "markdown"}
master_doc = "index"

exclude_patterns = [
    "_build", "Thumbs.db", ".DS_Store",
    # File-sync clients (iCloud Drive, OneDrive, Dropbox) leave "name 2.md"
    # copies behind when the exporter rewrites docs/pages and docs/news. Each
    # copy would otherwise be picked up as a real document and fail the -W
    # build as an orphan. The exporter deletes them too, but it cannot catch
    # copies the sync client writes after it has finished.
    "**/* [0-9].md",
]

# The export contains bare URLs in tables that read better as live links, and
# the portal's own headings need anchors so cross-page links keep working.
myst_enable_extensions = ["linkify", "deflist", "attrs_inline"]
myst_heading_anchors = 3

html_theme = "furo"
html_title = "European Air Quality Portal"
html_static_path = ["_static"]

# Every link that leaves these docs opens in a new tab, so the reader never
# loses their place — this is how the embedded viewers behave on the portal.
html_js_files = ["external-links.js"]
html_css_files = ["custom.css"]

# Set these once the repository has a real URL to enable furo's "edit this
# page" links:
#   html_theme_options = {
#       "source_repository": "https://github.com/<owner>/<repo>/",
#       "source_branch": "main",
#       "source_directory": "docs/",
#   }

# Bare-URL link checking is noisy against the Tableau host, which rejects
# HEAD requests from the linkchecker.
linkcheck_ignore = [
    r"https://tableau-public\.discomap\.eea\.europa\.eu/.*",
]
linkcheck_timeout = 20
