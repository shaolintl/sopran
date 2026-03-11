# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Static portfolio website for soprano Irina Kalderon. Deployed via GitHub Pages at `irina.kalderon.libal.info`. No build step, no package manager, no server-side code — pure HTML/CSS served directly.

## Development

There is no build, lint, or test process. Edit `.html` and `.css` files directly. To preview locally, open any HTML file in a browser or use a local static server (e.g. `python3 -m http.server`).

Deployment happens automatically via GitHub Pages on push to `main`.

## Architecture

**Pages:** Six standalone HTML files, each self-contained with its own `<head>`, navbar, content, and footer:
- `index.html` — redirect to `home.html`
- `home.html` — landing page with hero section
- `biography.html` — professional background
- `projects.html` — ensemble and collaboration details
- `concerts.html` — upcoming and past concert listings
- `media.html` — tabbed interface (videos, photo gallery, posters)
- `contact.html` — contact form (submits to FormBold)

**Shared patterns duplicated across all pages:**
- Navbar and footer markup are copy-pasted into each file (no templating)
- External deps loaded via CDN in each file: Bootstrap 5.3.3, Google Fonts (Cormorant Garamond, Inter)
- All custom styling lives in `css/custom.css`

**CSS theming** uses CSS custom properties defined in `:root` in `custom.css`:
- `--main-bg`, `--main-text`, `--secondary-text`, `--accent`, `--card-bg`
- Two-font system: Cormorant Garamond (headings), Inter (body)

**SEO:** Every page includes JSON-LD structured data (`<script type="application/ld+json">`), canonical URLs, meta descriptions, and robots directives. The `sitemap.xml` lists all six pages.

**Assets:** Images in `assets/photos/gallery/`, `assets/photos/projects/`, `assets/photos/posters/` (PDFs). Hero image is `assets/hero.webp`.

## Key Conventions

- When editing the navbar or footer, the same change must be made in all six HTML files.
- Concert entries in `concerts.html` include both HTML card markup and corresponding JSON-LD `MusicEvent` structured data — both must be updated together.
- When adding new pages, update `sitemap.xml` and add the navbar link to all existing pages.
- Images use `loading="lazy"` for performance.
- The site uses responsive Bootstrap grid with custom breakpoints at 900px, 767px, and 576px in `custom.css`.
- HTML files use `<!-- MARKER -->` comments to delimit editable sections for `manage.py`. Do not remove these markers.

## Management CLI (`manage.py`)

A Python 3 script (stdlib only) for common content updates. Run from the repo root:

```
python3 manage.py <command>
```

**Commands:**
- `concert` — Add a new upcoming concert (interactive prompts for title, date, time, location, venue, description, ticket URL). Inserts card chronologically and adds JSON-LD.
- `highlight` — Update the hero highlight image on `home.html` to the highest-numbered `assets/photos/highlight*.{jpg,png,webp}` file.
- `change` — Edit an existing concert (upcoming or past). Lists all concerts, prompts for field changes, updates HTML and JSON-LD.
- `photos` — Detect new gallery photos and posters not yet linked in `media.html`. Prompts for title/description for gallery photos; posters are auto-added.
- `video` — Add a YouTube video to `media.html`. Extracts video ID, checks for duplicates, inserts at top of videos section.
- `push` — Show `git status`/diff, prompt for commit message, then `git add -A && git commit && git push origin main`.

**Auto-archive:** Every command that touches `concerts.html` automatically moves expired upcoming concerts to the past section.

**Validation:** After every HTML edit, the script checks tag balance, marker presence, and JSON-LD validity.

**Backups:** Creates `.bak` files before writing (excluded via `.gitignore`).
