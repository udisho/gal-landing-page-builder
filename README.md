# Gal Travels — Landing Page Builder

A browser-only tool that turns an existing landing page HTML into a styled Gal Travels landing page, ready to paste into Ravpage.

## How to use

1. Open the live builder: **[https://udisho.github.io/gal-landing-page-builder/builder.html](https://udisho.github.io/gal-landing-page-builder/builder.html)**
2. Paste the full HTML of an existing landing page into the textarea, or send it in with the bookmarklet.
3. (Optional) pick a color palette, or click the two color boxes to define a custom one.
4. Click **Generate** — a preview appears below.
5. Click **Download .html** and paste the file contents into ravpage's HTML block.

## What it extracts automatically

- Trip name (`נחל X`) and age range
- Hero and info images, preferring real page images over Ravpage thumbnail screenshots
- Payment links (Green Invoice / ravpage checkout) — mapped to women-single / women-couple / men by Hebrew keywords near the link
- Prices (₪ numbers split into singles < 400 and couples ≥ 400)
- Day of week, trip date, start/end times, distance

Missing values fall back to sensible defaults so the output never breaks.

## Local development

```bash
python3 serve_gal.py 8090
# Open http://localhost:8090/builder
```

The local server adds a `/api/fetch?url=` proxy so you can fetch remote pages via URL during development. The published GitHub Pages version stays static, so the main browser flow there is paste HTML or use the bookmarklet.

## Files

- `builder.html` — the tool UI + extraction logic
- `template.html` — the landing-page template with `{{TOKENS}}` for trip data and colors
- `serve_gal.py` — local dev server with URL-fetch proxy
