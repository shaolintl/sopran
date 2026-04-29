#!/usr/bin/env python3
"""Website management CLI for Irina Kalderon's soprano portfolio site.

Usage:
    python3 manage.py concert    — Add a new upcoming concert
    python3 manage.py highlight  — Update hero highlight image on home page
    python3 manage.py change     — Edit an existing concert
    python3 manage.py photos     — Add new gallery photos and posters
    python3 manage.py video      — Add a YouTube video
    python3 manage.py push       — Commit and push changes
"""

import copy
import datetime
import json
import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONCERTS_HTML = os.path.join(BASE_DIR, "concerts.html")
HOME_HTML = os.path.join(BASE_DIR, "home.html")
MEDIA_HTML = os.path.join(BASE_DIR, "media.html")

SITE_URL = "https://irina.kalderon.libal.info"

# ── Month dictionaries (French + English) ──────────────────────────────

MONTH_TO_NUM = {
    # English
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    # French
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4,
    "mai": 5, "juin": 6, "juillet": 7, "août": 8, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

NUM_TO_MONTH_EN = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

# ── Core utilities ──────────────────────────────────────────────────────

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    """Write content to path, creating a .bak backup first."""
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def extract_section(html, start_marker, end_marker):
    """Return the text between start_marker and end_marker (exclusive)."""
    s = html.find(start_marker)
    if s == -1:
        raise ValueError(f"Marker not found: {start_marker}")
    s += len(start_marker)
    e = html.find(end_marker, s)
    if e == -1:
        raise ValueError(f"Marker not found: {end_marker}")
    return html[s:e]


def replace_section(html, start_marker, end_marker, new_content):
    """Replace the text between start_marker and end_marker with new_content."""
    s = html.find(start_marker)
    if s == -1:
        raise ValueError(f"Marker not found: {start_marker}")
    s += len(start_marker)
    e = html.find(end_marker, s)
    if e == -1:
        raise ValueError(f"Marker not found: {end_marker}")
    return html[:s] + new_content + html[e:]


# ── Date handling ───────────────────────────────────────────────────────

def parse_display_date(text):
    """Parse date strings like 'Mars 7 2026', 'April 25 2026', 'August 27,28 2026'.

    For multi-day dates (comma-separated days), returns the last day for archiving.
    Returns a datetime.date or None.
    """
    text = text.strip()
    parts = text.split()
    if len(parts) < 3:
        return None
    month_str = parts[0].lower()
    day_str = parts[1].rstrip(",")
    year_str = parts[2]

    month = MONTH_TO_NUM.get(month_str)
    if month is None:
        return None

    # Handle multi-day: "27,28" -> use last day
    days = day_str.split(",")
    try:
        day = int(days[-1])
        year = int(year_str)
    except ValueError:
        return None

    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


# ── Concert dataclass and parsing ───────────────────────────────────────

@dataclass
class Concert:
    title: str = ""
    date_text: str = ""
    time_text: str = ""
    location_text: str = ""
    venue: str = ""
    description: str = ""
    button_html: str = ""
    parsed_date: Optional[datetime.date] = None

    def __post_init__(self):
        if self.parsed_date is None and self.date_text:
            self.parsed_date = parse_display_date(self.date_text)


def parse_concert_cards(section_html):
    """Parse concert-card divs from a section of HTML. Returns list of Concert."""
    concerts = []
    # Match each concert-card div block
    pattern = re.compile(
        r'<div\s+class="concert-card">\s*'
        r'<div\s+class="concert-title">(.*?)</div>\s*'
        r'<div\s+class="concert-meta">(.*?)</div>\s*'
        r'(.*?)'
        r'</div>',
        re.DOTALL
    )
    for m in pattern.finditer(section_html):
        title = m.group(1).strip()
        meta_html = m.group(2).strip()
        body = m.group(3).strip()

        # Parse meta spans
        spans = re.findall(r'<span>(.*?)</span>', meta_html)
        date_text = spans[0] if len(spans) > 0 else ""
        # Figure out time vs location - if 2 spans it's date + location, if 3+ it's date + time + location
        time_text = ""
        location_text = ""
        if len(spans) == 2:
            location_text = spans[1]
        elif len(spans) >= 3:
            time_text = spans[1]
            location_text = spans[2]

        # Parse body: venue line, description <p>, button
        venue = ""
        description = ""
        button_html = ""

        venue_m = re.search(r'<strong>Venue:</strong>\s*(.*?)<br>', body)
        if venue_m:
            venue = venue_m.group(1).strip()

        desc_m = re.search(r'<p>(.*?)</p>', body, re.DOTALL)
        if desc_m:
            description = desc_m.group(1).strip()

        btn_m = re.search(r'(<(?:a|button)\s+class="btn\b.*?(?:</a>|</button>))', body, re.DOTALL)
        if btn_m:
            button_html = btn_m.group(1).strip()

        concerts.append(Concert(
            title=title,
            date_text=date_text,
            time_text=time_text,
            location_text=location_text,
            venue=venue,
            description=description,
            button_html=button_html,
        ))
    return concerts


def render_concert_card(concert, indent="    "):
    """Render a Concert back to an HTML card matching existing patterns."""
    lines = []
    lines.append(f'{indent}<div class="concert-card">')
    lines.append(f'{indent}  <div class="concert-title">{concert.title}</div>')

    meta_spans = f'<span>{concert.date_text}</span>'
    if concert.time_text:
        meta_spans += f'<span>{concert.time_text}</span>'
    if concert.location_text:
        meta_spans += f'<span>{concert.location_text}</span>'
    lines.append(f'{indent}  <div class="concert-meta">{meta_spans}</div>')

    if concert.venue:
        lines.append(f'{indent}  <strong>Venue:</strong> {concert.venue}<br>')
    else:
        lines.append(f'{indent}  <br>')

    if concert.description:
        lines.append(f'{indent}  <p>{concert.description}</p>')

    if concert.button_html:
        lines.append(f'{indent}  {concert.button_html}')

    lines.append(f'{indent}</div>')
    return "\n".join(lines)


# ── JSON-LD handling ────────────────────────────────────────────────────

def parse_jsonld_events(html):
    """Parse the MusicEvent JSON-LD block from concerts.html. Returns (json_obj, raw_script_text)."""
    section = extract_section(html, "<!-- JSONLD_START -->", "<!-- JSONLD_END -->")
    # Find the JSON inside <script> tags
    m = re.search(r'<script\s+type="application/ld\+json">\s*(.*?)\s*</script>', section, re.DOTALL)
    if not m:
        return None, section
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None, section
    return data, section


def concert_to_jsonld(concert):
    """Convert a Concert to a JSON-LD MusicEvent dict."""
    d = concert.parsed_date
    if d is None:
        d = datetime.date.today()

    # Default time
    time_str = concert.time_text.strip() if concert.time_text else "19:00"
    # Parse HH:MM
    tm = re.match(r'(\d{1,2}):(\d{2})', time_str)
    if tm:
        hour, minute = int(tm.group(1)), int(tm.group(2))
    else:
        hour, minute = 19, 0

    start_dt = datetime.datetime(d.year, d.month, d.day, hour, minute)
    end_dt = start_dt + datetime.timedelta(hours=2)

    # Parse location
    loc_parts = [p.strip() for p in concert.location_text.split(",")]
    city = loc_parts[0] if loc_parts else ""
    country = loc_parts[1] if len(loc_parts) > 1 else ""

    # Map country to code
    country_codes = {
        "luxembourg": "LU", "france": "FR", "germany": "DE",
        "belgium": "BE", "austria": "AT", "italy": "IT",
        "uk": "GB", "united kingdom": "GB", "netherlands": "NL",
        "spain": "ES", "portugal": "PT", "switzerland": "CH",
        "bulgaria": "BG", "czech republic": "CZ", "czechia": "CZ",
    }
    country_code = country_codes.get(country.lower(), country.upper()[:2]) if country else "LU"

    event = {
        "@type": "MusicEvent",
        "name": concert.title,
        "startDate": start_dt.strftime("%Y-%m-%dT%H:%M:%S+02:00"),
        "endDate": end_dt.strftime("%Y-%m-%dT%H:%M:%S+02:00"),
        "location": {
            "@type": "Place",
            "name": concert.venue or city,
            "address": {
                "@type": "PostalAddress",
                "addressLocality": city,
                "addressCountry": country_code,
            }
        },
        "performer": {
            "@type": "Person",
            "name": "Irina Kalderon"
        },
        "url": f"{SITE_URL}/concerts.html"
    }
    return event


def render_jsonld_block(data):
    """Render the full JSON-LD script block."""
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    return f'\n  <script type="application/ld+json">\n{json_str}\n  </script>\n  '


def update_jsonld_events(html, events_data):
    """Replace the JSON-LD block in html with updated events_data."""
    new_block = render_jsonld_block(events_data)
    return replace_section(html, "<!-- JSONLD_START -->", "<!-- JSONLD_END -->", new_block)


# ── Auto-archive ────────────────────────────────────────────────────────

def auto_archive(html):
    """Move expired upcoming concerts to past section. Returns modified html."""
    today = datetime.date.today()

    upcoming_section = extract_section(html, "<!-- UPCOMING_START -->", "<!-- UPCOMING_END -->")
    past_section = extract_section(html, "<!-- PAST_START -->", "<!-- PAST_END -->")

    upcoming = parse_concert_cards(upcoming_section)
    past = parse_concert_cards(past_section)

    still_upcoming = []
    newly_past = []

    for c in upcoming:
        if c.parsed_date and c.parsed_date < today:
            newly_past.append(c)
        else:
            still_upcoming.append(c)

    if not newly_past:
        return html  # Nothing to archive

    print(f"  Auto-archiving {len(newly_past)} past concert(s)...")
    for c in newly_past:
        print(f"    - {c.title} ({c.date_text})")

    # Insert newly past concerts at top of past section, sorted by date descending
    newly_past.sort(key=lambda c: c.parsed_date or datetime.date.min, reverse=True)
    all_past = newly_past + past

    # Re-render upcoming
    if still_upcoming:
        new_upcoming = "\n" + "\n".join(render_concert_card(c) for c in still_upcoming) + "\n    "
    else:
        new_upcoming = "\n    "

    # Re-render past
    if all_past:
        new_past = "\n" + "\n".join(render_concert_card(c, indent="   ") for c in all_past) + "\n    "
    else:
        new_past = "\n    "

    html = replace_section(html, "<!-- UPCOMING_START -->", "<!-- UPCOMING_END -->", new_upcoming)
    html = replace_section(html, "<!-- PAST_START -->", "<!-- PAST_END -->", new_past)

    # Update year in Past Concerts heading if needed
    current_year = str(today.year)
    html = re.sub(
        r'(<h1>Past Concerts\s*)\(\d{4}\)',
        rf'\1({current_year})',
        html
    )

    return html


# ── Post-edit validation ────────────────────────────────────────────────

def post_edit_validation(path):
    """Run validation checks on an edited HTML file."""
    html = read_file(path)
    errors = []

    # Check balanced tags
    for tag in ["div", "section", "script"]:
        opens = len(re.findall(rf'<{tag}[\s>]', html))
        closes = len(re.findall(rf'</{tag}>', html))
        if opens != closes:
            errors.append(f"Unbalanced <{tag}>: {opens} opens vs {closes} closes")

    # Verify markers still present
    basename = os.path.basename(path)
    if basename == "concerts.html":
        markers = ["UPCOMING_START", "UPCOMING_END", "PAST_START", "PAST_END",
                    "JSONLD_START", "JSONLD_END"]
    elif basename == "home.html":
        markers = ["HIGHLIGHT_START", "HIGHLIGHT_END"]
    elif basename == "media.html":
        markers = ["VIDEOS_START", "VIDEOS_END", "PHOTOS_START", "PHOTOS_END",
                    "POSTERS_START", "POSTERS_END"]
    else:
        markers = []

    for marker in markers:
        if f"<!-- {marker} -->" not in html:
            errors.append(f"Missing marker: <!-- {marker} -->")

    # Validate JSON-LD blocks
    for m in re.finditer(r'<script\s+type="application/ld\+json">\s*(.*?)\s*</script>', html, re.DOTALL):
        try:
            json.loads(m.group(1))
        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON-LD: {e}")

    if errors:
        print("\n⚠ Validation warnings:")
        for err in errors:
            print(f"  - {err}")
    else:
        print("✓ Validation passed")

    # Show git diff
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", path],
            capture_output=True, text=True, cwd=BASE_DIR
        )
        if result.stdout.strip():
            print(f"\n  Git diff:\n{result.stdout}")
    except FileNotFoundError:
        pass

    return len(errors) == 0


# ── Command: concert ────────────────────────────────────────────────────

def cmd_concert():
    """Interactively add a new upcoming concert."""
    print("=== Add New Concert ===\n")

    title = input("Concert title: ").strip()
    if not title:
        print("Title is required.")
        return

    date_text = input("Date (e.g. 'April 25 2026' or 'August 27,28 2026'): ").strip()
    if not date_text:
        print("Date is required.")
        return

    time_text = input("Time (e.g. '19:30', or Enter to skip): ").strip()
    location_text = input("Location (e.g. 'Luxembourg, Luxembourg'): ").strip()
    venue = input("Venue name: ").strip()
    description = input("Description (or Enter to skip): ").strip()
    ticket_url = input("Ticket URL (or Enter to skip): ").strip()

    button_html = ""
    if ticket_url:
        button_html = f'<a class="btn btn-main mt-2" href="{ticket_url}">Get Tickets</a>'

    concert = Concert(
        title=title,
        date_text=date_text,
        time_text=time_text,
        location_text=location_text,
        venue=venue,
        description=description,
        button_html=button_html,
    )

    html = read_file(CONCERTS_HTML)

    # Auto-archive first
    html = auto_archive(html)

    # Parse existing upcoming concerts
    upcoming_section = extract_section(html, "<!-- UPCOMING_START -->", "<!-- UPCOMING_END -->")
    upcoming = parse_concert_cards(upcoming_section)

    # Insert in chronological order
    upcoming.append(concert)
    upcoming.sort(key=lambda c: c.parsed_date or datetime.date.max)

    # Re-render upcoming
    new_upcoming = "\n" + "\n".join(render_concert_card(c) for c in upcoming) + "\n    "
    html = replace_section(html, "<!-- UPCOMING_START -->", "<!-- UPCOMING_END -->", new_upcoming)

    # Add JSON-LD event
    events_data, _ = parse_jsonld_events(html)
    if events_data and "@graph" in events_data:
        events_data["@graph"].append(concert_to_jsonld(concert))
        html = update_jsonld_events(html, events_data)

    write_file(CONCERTS_HTML, html)
    print(f"\n✓ Added concert: {title}")
    post_edit_validation(CONCERTS_HTML)


# ── Command: highlight ──────────────────────────────────────────────────

def cmd_highlight():
    """Update the hero highlight image on home.html."""
    print("=== Update Highlight Image ===\n")

    photos_dir = os.path.join(BASE_DIR, "assets", "photos")
    highlights = sorted(glob.glob(os.path.join(photos_dir, "highlight*")))

    if not highlights:
        print("No highlight files found in assets/photos/")
        return

    # Find highest numbered highlight
    best = None
    best_num = -1
    for h in highlights:
        basename = os.path.basename(h)
        m = re.search(r'highlight(\d*)', basename)
        if m:
            num = int(m.group(1)) if m.group(1) else 0
            if num > best_num:
                best_num = num
                best = basename

    if best is None:
        print("No highlight files found.")
        return

    new_src = f"assets/photos/{best}"
    print(f"Found latest highlight: {best}")

    html = read_file(HOME_HTML)
    highlight_section = extract_section(html, "<!-- HIGHLIGHT_START -->", "<!-- HIGHLIGHT_END -->")

    # Replace the img src
    old_src_m = re.search(r'<img\s+src="([^"]*)"', highlight_section)
    if old_src_m:
        old_src = old_src_m.group(1)
        if old_src == new_src:
            print(f"Already using {best}. No change needed.")
            return
        new_section = highlight_section.replace(old_src, new_src)
        html = replace_section(html, "<!-- HIGHLIGHT_START -->", "<!-- HIGHLIGHT_END -->", new_section)
        write_file(HOME_HTML, html)
        print(f"✓ Updated highlight image: {old_src} → {new_src}")
        post_edit_validation(HOME_HTML)
    else:
        print("Could not find <img> tag in highlight section.")


# ── Command: change ─────────────────────────────────────────────────────

def cmd_change():
    """Edit an existing concert (upcoming or past)."""
    print("=== Edit Concert ===\n")

    html = read_file(CONCERTS_HTML)
    html = auto_archive(html)

    upcoming_section = extract_section(html, "<!-- UPCOMING_START -->", "<!-- UPCOMING_END -->")
    past_section = extract_section(html, "<!-- PAST_START -->", "<!-- PAST_END -->")

    upcoming = parse_concert_cards(upcoming_section)
    past = parse_concert_cards(past_section)

    all_concerts = []
    print("Upcoming:")
    for i, c in enumerate(upcoming):
        all_concerts.append(("upcoming", i, c))
        print(f"  {len(all_concerts)}. [{c.date_text}] {c.title}")

    print("\nPast:")
    for i, c in enumerate(past):
        all_concerts.append(("past", i, c))
        print(f"  {len(all_concerts)}. [{c.date_text}] {c.title}")

    if not all_concerts:
        print("No concerts found.")
        return

    choice = input(f"\nSelect concert to edit (1-{len(all_concerts)}): ").strip()
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(all_concerts):
            raise ValueError
    except ValueError:
        print("Invalid selection.")
        return

    section_type, orig_idx, concert = all_concerts[idx]

    print(f"\nEditing: {concert.title}")
    print("(Press Enter to keep current value)\n")

    new_title = input(f"  Title [{concert.title}]: ").strip() or concert.title
    new_date = input(f"  Date [{concert.date_text}]: ").strip() or concert.date_text
    new_time = input(f"  Time [{concert.time_text}]: ").strip() or concert.time_text
    new_location = input(f"  Location [{concert.location_text}]: ").strip() or concert.location_text
    new_venue = input(f"  Venue [{concert.venue}]: ").strip() or concert.venue
    new_desc = input(f"  Description [{concert.description[:50]}...]: ").strip() if concert.description else input("  Description: ").strip()
    if not new_desc and concert.description:
        new_desc = concert.description

    updated = Concert(
        title=new_title,
        date_text=new_date,
        time_text=new_time,
        location_text=new_location,
        venue=new_venue,
        description=new_desc,
        button_html=concert.button_html,
    )

    if section_type == "upcoming":
        upcoming[orig_idx] = updated
        upcoming.sort(key=lambda c: c.parsed_date or datetime.date.max)
        new_section = "\n" + "\n".join(render_concert_card(c) for c in upcoming) + "\n    "
        html = replace_section(html, "<!-- UPCOMING_START -->", "<!-- UPCOMING_END -->", new_section)
    else:
        past[orig_idx] = updated
        new_section = "\n" + "\n".join(render_concert_card(c, indent="   ") for c in past) + "\n    "
        html = replace_section(html, "<!-- PAST_START -->", "<!-- PAST_END -->", new_section)

    # Update JSON-LD: find matching event by old title and update
    events_data, _ = parse_jsonld_events(html)
    if events_data and "@graph" in events_data:
        for event in events_data["@graph"]:
            if event.get("name") == concert.title:
                new_event = concert_to_jsonld(updated)
                event.update(new_event)
                break
        html = update_jsonld_events(html, events_data)

    write_file(CONCERTS_HTML, html)
    print(f"\n✓ Updated concert: {new_title}")
    post_edit_validation(CONCERTS_HTML)


# ── Command: photos ─────────────────────────────────────────────────────

def cmd_photos():
    """Add new gallery photos and posters to media.html."""
    print("=== Add New Photos & Posters ===\n")

    html = read_file(MEDIA_HTML)

    # Find referenced gallery images
    photos_section = extract_section(html, "<!-- PHOTOS_START -->", "<!-- PHOTOS_END -->")
    referenced_gallery = set(re.findall(r'gallery/([^"]+)', photos_section))

    # Find referenced posters
    posters_section = extract_section(html, "<!-- POSTERS_START -->", "<!-- POSTERS_END -->")
    referenced_posters = set(re.findall(r'posters/([^"]+)', posters_section))

    # Scan filesystem
    gallery_dir = os.path.join(BASE_DIR, "assets", "photos", "gallery")
    poster_dir = os.path.join(BASE_DIR, "assets", "photos", "posters")

    gallery_files = set()
    if os.path.isdir(gallery_dir):
        for f in os.listdir(gallery_dir):
            if f.startswith("."):
                continue
            gallery_files.add(f)

    poster_files = set()
    if os.path.isdir(poster_dir):
        for f in os.listdir(poster_dir):
            if f.startswith("."):
                continue
            poster_files.add(f)

    new_gallery = sorted(gallery_files - referenced_gallery)
    new_posters = sorted(poster_files - referenced_posters)

    if not new_gallery and not new_posters:
        print("No new photos or posters found. Everything is already linked.")
        return

    # Process new gallery photos
    added_gallery = 0
    if new_gallery:
        print(f"Found {len(new_gallery)} new gallery photo(s):\n")
        for f in new_gallery:
            ext = os.path.splitext(f)[1].lower()
            if ext == ".heic":
                print(f"  ⚠ Skipping {f} (.heic not supported by browsers — convert to .jpg first)")
                continue

            print(f"  File: {f}")
            title = input(f"    Title (e.g. 'Opera Performance'): ").strip()
            if not title:
                print("    Skipped (no title provided)")
                continue
            desc = input(f"    Description (e.g. 'CAPE, Luxembourg 2025'): ").strip()

            card_html = f"""          <div class="col-md-4">
            <div class="media-card">
              <div class="media-img">
                <img src="assets/photos/gallery/{f}" alt="{title}" class="img-fluid rounded" loading="lazy">
              </div>
              <div class="media-desc">
                <strong>{title}</strong><br>
                {desc}
              </div>
            </div>
          </div>"""

            # Append before PHOTOS_END
            photos_section = extract_section(html, "<!-- PHOTOS_START -->", "<!-- PHOTOS_END -->")
            new_photos_section = photos_section + card_html + "\n          "
            html = replace_section(html, "<!-- PHOTOS_START -->", "<!-- PHOTOS_END -->", new_photos_section)
            added_gallery += 1
            print(f"    ✓ Added {f}")

    # Process new posters (auto-add, no metadata needed)
    added_posters = 0
    if new_posters:
        print(f"\nFound {len(new_posters)} new poster(s):")
        for f in new_posters:
            card_html = f"""          <div class="col-md-4">
            <div class="media-card">
              <div class="media-img">
                <embed src="assets/photos/posters/{f}" type="application/pdf" width="100%" height="600px">
              </div>
            </div>
          </div>"""

            posters_section = extract_section(html, "<!-- POSTERS_START -->", "<!-- POSTERS_END -->")
            new_posters_section = posters_section + card_html + "\n          "
            html = replace_section(html, "<!-- POSTERS_START -->", "<!-- POSTERS_END -->", new_posters_section)
            added_posters += 1
            print(f"  ✓ Added {f}")

    if added_gallery > 0 or added_posters > 0:
        write_file(MEDIA_HTML, html)
        print(f"\n✓ Added {added_gallery} photo(s) and {added_posters} poster(s)")
        post_edit_validation(MEDIA_HTML)
    else:
        print("\nNo changes made.")


# ── Command: video ──────────────────────────────────────────────────────

def cmd_video():
    """Add a YouTube video to media.html."""
    print("=== Add YouTube Video ===\n")

    url = input("YouTube URL: ").strip()
    if not url:
        print("URL is required.")
        return

    # Extract video ID from various URL formats
    video_id = None
    patterns = [
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            video_id = m.group(1)
            break

    if not video_id:
        print("Could not extract video ID from URL.")
        return

    embed_url = f"https://www.youtube.com/embed/{video_id}"
    html = read_file(MEDIA_HTML)

    # Check for duplicates
    if video_id in html:
        print(f"Video {video_id} is already on the page.")
        return

    video_html = f"""
          <div class="col-md-4">
            <div class="ratio ratio-16x9">
              <iframe src="{embed_url}" title="YouTube video" allowfullscreen allow="autoplay; encrypted-media"></iframe>
            </div>
          </div>"""

    # Insert at top of videos section (newest first)
    videos_section = extract_section(html, "<!-- VIDEOS_START -->", "<!-- VIDEOS_END -->")
    new_videos_section = video_html + videos_section
    html = replace_section(html, "<!-- VIDEOS_START -->", "<!-- VIDEOS_END -->", new_videos_section)

    write_file(MEDIA_HTML, html)
    print(f"✓ Added video: {embed_url}")
    post_edit_validation(MEDIA_HTML)


# ── Command: push ───────────────────────────────────────────────────────

def cmd_push():
    """Show status, prompt for commit message, commit and push."""
    print("=== Git Push ===\n")

    # Show status
    result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=BASE_DIR)
    if not result.stdout.strip():
        print("No changes to commit.")
        return

    print("Changed files:")
    print(result.stdout)

    # Show diff summary
    result = subprocess.run(["git", "diff", "--stat"], capture_output=True, text=True, cwd=BASE_DIR)
    if result.stdout.strip():
        print("Diff summary:")
        print(result.stdout)

    result = subprocess.run(["git", "diff", "--cached", "--stat"], capture_output=True, text=True, cwd=BASE_DIR)
    if result.stdout.strip():
        print("Staged diff summary:")
        print(result.stdout)

    msg = input("\nCommit message: ").strip()
    if not msg:
        print("Commit message is required.")
        return

    confirm = input(f"Commit and push with message '{msg}'? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    # Stage, commit, push
    subprocess.run(["git", "add", "-A"], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=BASE_DIR, check=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=BASE_DIR, check=True)
    print("\n✓ Pushed to origin/main")


# ── Main ────────────────────────────────────────────────────────────────

COMMANDS = {
    "concert": cmd_concert,
    "highlight": cmd_highlight,
    "change": cmd_change,
    "photos": cmd_photos,
    "video": cmd_video,
    "push": cmd_push,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print("Available commands:", ", ".join(COMMANDS.keys()))
        sys.exit(1)

    cmd = sys.argv[1]
    COMMANDS[cmd]()


if __name__ == "__main__":
    main()
