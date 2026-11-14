"""
Generates production-grade, beautifully styled HTML legal pages from
qumail_privacy_policy.md and qumail_terms_and_conditions.md.
Outputs into frontend/public/ and frontend/dist/ so they can be opened in a
fresh browser tab seamlessly via window.open('/privacy-policy.html', '_blank')
and window.open('/terms-and-conditions.html', '_blank').
"""

import os
import re
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = ROOT / "frontend" / "public"
DIST_DIR = ROOT / "frontend" / "dist"

PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
DIST_DIR.mkdir(parents=True, exist_ok=True)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{page_title} — QuMail Legal &amp; Compliance</title>
  <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%230B57D0'><path d='M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5zm-2 16l-4-4 1.41-1.41L10 15.17l6.59-6.59L18 10l-8 8z'/></svg>">
  <style>
    :root {{
      --bg: #F8FAFC;
      --card-bg: #FFFFFF;
      --text: #1E293B;
      --text-muted: #64748B;
      --border: #E2E8F0;
      --primary: #0B57D0;
      --primary-hover: #0842A0;
      --primary-subtle: #EFF6FF;
      --accent: #4F46E5;
      --badge-bg: #EEF2FF;
      --badge-text: #4338CA;
      --badge-border: #C7D2FE;
      --h1-color: #0F172A;
      --h2-color: #1E293B;
      --h3-color: #334155;
      --hr-color: #E2E8F0;
      --code-bg: #F1F5F9;
      --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05), 0 2px 4px -2px rgb(0 0 0 / 0.05);
      --header-bg: rgba(255, 255, 255, 0.85);
    }}

    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #090D16;
        --card-bg: #111726;
        --text: #E2E8F0;
        --text-muted: #94A3B8;
        --border: #1E293B;
        --primary: #38BDF8;
        --primary-hover: #0EA5E9;
        --primary-subtle: #0C4A6E;
        --accent: #818CF8;
        --badge-bg: #1E1B4B;
        --badge-text: #A5B4FC;
        --badge-border: #3730A3;
        --h1-color: #F8FAFC;
        --h2-color: #F1F5F9;
        --h3-color: #E2E8F0;
        --hr-color: #1E293B;
        --code-bg: #1E293B;
        --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.4);
        --header-bg: rgba(17, 23, 38, 0.88);
      }}
    }}

    body[data-theme="light"] {{
      --bg: #F8FAFC;
      --card-bg: #FFFFFF;
      --text: #1E293B;
      --text-muted: #64748B;
      --border: #E2E8F0;
      --primary: #0B57D0;
      --primary-hover: #0842A0;
      --primary-subtle: #EFF6FF;
      --accent: #4F46E5;
      --badge-bg: #EEF2FF;
      --badge-text: #4338CA;
      --badge-border: #C7D2FE;
      --h1-color: #0F172A;
      --h2-color: #1E293B;
      --h3-color: #334155;
      --hr-color: #E2E8F0;
      --code-bg: #F1F5F9;
      --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05);
      --header-bg: rgba(255, 255, 255, 0.85);
    }}

    body[data-theme="dark"] {{
      --bg: #090D16;
      --card-bg: #111726;
      --text: #E2E8F0;
      --text-muted: #94A3B8;
      --border: #1E293B;
      --primary: #38BDF8;
      --primary-hover: #0EA5E9;
      --primary-subtle: #0C4A6E;
      --accent: #818CF8;
      --badge-bg: #1E1B4B;
      --badge-text: #A5B4FC;
      --badge-border: #3730A3;
      --h1-color: #F8FAFC;
      --h2-color: #F1F5F9;
      --h3-color: #E2E8F0;
      --hr-color: #1E293B;
      --code-bg: #1E293B;
      --shadow: 0 4px 6px -1px rgb(0 0 0 / 0.4);
      --header-bg: rgba(17, 23, 38, 0.88);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.7;
      font-size: 15px;
      -webkit-font-smoothing: antialiased;
      transition: background-color 0.2s ease, color 0.2s ease;
    }}

    .top-bar {{
      position: sticky;
      top: 0;
      z-index: 100;
      background: var(--header-bg);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .brand-group {{
      display: flex;
      align-items: center;
      gap: 12px;
      text-decoration: none;
      color: inherit;
    }}

    .brand-icon {{
      width: 34px;
      height: 34px;
      border-radius: 10px;
      background: linear-gradient(135deg, #0B57D0, #4F46E5);
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: bold;
      box-shadow: 0 2px 6px rgba(11, 87, 208, 0.3);
    }}

    .brand-icon svg {{
      width: 20px;
      height: 20px;
      fill: currentColor;
    }}

    .brand-title {{
      font-size: 16px;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: var(--h1-color);
    }}

    .brand-subtitle {{
      font-size: 11px;
      color: var(--text-muted);
      font-weight: 500;
    }}

    .actions-group {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 7px 14px;
      font-size: 12px;
      font-weight: 600;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--card-bg);
      color: var(--text);
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s ease;
    }}

    .btn:hover {{
      background: var(--primary-subtle);
      border-color: var(--primary);
      color: var(--primary);
    }}

    .btn-primary {{
      background: var(--primary);
      color: white;
      border-color: var(--primary);
    }}

    .btn-primary:hover {{
      background: var(--primary-hover);
      color: white;
    }}

    .main-container {{
      max-width: 860px;
      margin: 32px auto 80px auto;
      padding: 0 24px;
    }}

    .doc-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 48px;
      box-shadow: var(--shadow);
    }}

    .doc-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      background: var(--badge-bg);
      color: var(--badge-text);
      border: 1px solid var(--badge-border);
      margin-bottom: 16px;
    }}

    .doc-h1 {{
      font-size: 30px;
      font-weight: 800;
      letter-spacing: -0.02em;
      color: var(--h1-color);
      margin-bottom: 12px;
      line-height: 1.25;
    }}

    .doc-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      padding-bottom: 24px;
      margin-bottom: 28px;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      color: var(--text-muted);
    }}

    .doc-meta span strong {{
      color: var(--text);
    }}

    .doc-h2 {{
      font-size: 20px;
      font-weight: 700;
      color: var(--h2-color);
      margin-top: 36px;
      margin-bottom: 14px;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--border);
      letter-spacing: -0.01em;
    }}

    .doc-h3 {{
      font-size: 16px;
      font-weight: 600;
      color: var(--h3-color);
      margin-top: 24px;
      margin-bottom: 10px;
    }}

    .doc-p {{
      margin-bottom: 14px;
      color: var(--text);
    }}

    .doc-ul {{
      margin: 12px 0 18px 24px;
      color: var(--text);
    }}

    .doc-ul li {{
      margin-bottom: 6px;
    }}

    .doc-link {{
      color: var(--primary);
      text-decoration: underline;
      text-underline-offset: 3px;
    }}

    .doc-link:hover {{
      color: var(--primary-hover);
    }}

    .doc-divider {{
      border: none;
      border-top: 1px solid var(--hr-color);
      margin: 32px 0;
    }}

    .footer-nav {{
      margin-top: 40px;
      padding-top: 24px;
      border-top: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 13px;
      color: var(--text-muted);
    }}

    @media print {{
      .top-bar, .actions-group, .footer-nav {{
        display: none !important;
      }}
      .doc-card {{
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
      }}
      body {{
        background: white !important;
        color: black !important;
      }}
    }}
  </style>
</head>
<body>
  <header class="top-bar">
    <a href="#" class="brand-group">
      <div class="brand-icon">
        <svg viewBox="0 0 24 24"><path d="M12 2L3 7v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-9-5zm-2 16l-4-4 1.41-1.41L10 15.17l6.59-6.59L18 10l-8 8z"/></svg>
      </div>
      <div>
        <div class="brand-title">QuMail 1.0</div>
        <div class="brand-subtitle">Official Legal &amp; Compliance Portal</div>
      </div>
    </a>
    <div class="actions-group">
      <a href="{other_url}" class="btn">
        <span>{other_title}</span> &rarr;
      </a>
      <button class="btn" onclick="window.print()">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9V2h12v7M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2M6 14h12v8H6z"/></svg>
        <span>Print</span>
      </button>
      <button class="btn btn-primary" onclick="window.close()">
        <span>Close Tab</span>
      </button>
    </div>
  </header>

  <main class="main-container">
    <article class="doc-card">
      <div class="doc-badge">Official QuMail Agreement</div>
      {rendered_content}
      
      <div class="footer-nav">
        <div>&copy; 2026 QuMail Project Team · All Rights Reserved.</div>
        <div>
          <a href="{other_url}" class="doc-link">{other_title}</a>
        </div>
      </div>
    </article>
  </main>
</body>
</html>
"""


def convert_markdown_to_body(md_text: str) -> str:
    lines = md_text.splitlines()
    out = []
    i = 0
    in_list = False

    def inline_format(t: str) -> str:
        # First normalize escaped periods like 1\.
        t = t.replace(r"\.", ".")
        # Escape html chars
        t = html.escape(t)
        # Bold **text**
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        # Italic *text*
        t = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", t)
        # Links [label](url)
        t = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" rel="noopener noreferrer" class="doc-link">\1</a>',
            t,
        )
        return t

    while i < len(lines):
        line = lines[i].rstrip()
        stripped = line.strip()

        # Check setext h1
        if i + 1 < len(lines) and re.match(r"^={3,}$", lines[i + 1].strip()) and stripped:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<h1 class="doc-h1">{inline_format(stripped)}</h1>')
            i += 2
            continue

        # Check setext h2
        if (
            i + 1 < len(lines)
            and re.match(r"^-{3,}$", lines[i + 1].strip())
            and stripped
            and not stripped.startswith(("*", "-", "#"))
        ):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<h2 class="doc-h2">{inline_format(stripped)}</h2>')
            i += 2
            continue

        # ATX h3
        if stripped.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<h3 class="doc-h3">{inline_format(stripped[4:])}</h3>')
            i += 1
            continue

        # ATX h2
        if stripped.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<h2 class="doc-h2">{inline_format(stripped[3:])}</h2>')
            i += 1
            continue

        # ATX h1
        if stripped.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f'<h1 class="doc-h1">{inline_format(stripped[2:])}</h1>')
            i += 1
            continue

        # Divider
        if re.match(r"^(\*{3,}|-{3,}|_{3,})$", stripped):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append('<hr class="doc-divider" />')
            i += 1
            continue

        # Bullets (* or -)
        bullet_match = re.match(r"^[*-]\s+(.+)$", stripped)
        if bullet_match:
            if not in_list:
                out.append('<ul class="doc-ul">')
                in_list = True
            out.append(f"<li>{inline_format(bullet_match.group(1))}</li>")
            i += 1
            continue

        # Blank line
        if not stripped:
            if in_list:
                out.append("</ul>")
                in_list = False
            i += 1
            continue

        # Regular paragraph
        if in_list:
            out.append("</ul>")
            in_list = False
        out.append(f'<p class="doc-p">{inline_format(stripped)}</p>')
        i += 1

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


def main():
    privacy_md = (ROOT / "qumail_privacy_policy.md").read_text(encoding="utf-8")
    terms_md = (ROOT / "qumail_terms_and_conditions.md").read_text(encoding="utf-8")

    privacy_body = convert_markdown_to_body(privacy_md)
    terms_body = convert_markdown_to_body(terms_md)

    privacy_html = HTML_TEMPLATE.format(
        page_title="Privacy Policy",
        rendered_content=privacy_body,
        other_title="Terms & Conditions",
        other_url="terms-and-conditions.html",
    )

    terms_html = HTML_TEMPLATE.format(
        page_title="Terms & Conditions",
        rendered_content=terms_body,
        other_title="Privacy Policy",
        other_url="privacy-policy.html",
    )

    for target_dir in [PUBLIC_DIR, DIST_DIR]:
        (target_dir / "privacy-policy.html").write_text(privacy_html, encoding="utf-8")
        (target_dir / "terms-and-conditions.html").write_text(terms_html, encoding="utf-8")

    print(f"Generated legal pages in {PUBLIC_DIR} and {DIST_DIR}")


if __name__ == "__main__":
    main()
