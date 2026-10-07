#!/usr/bin/env python3
"""Convert a WordPress REST API dump into a Jekyll site."""

import html
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse
import urllib.request

RAW = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2])
SITE_HOST = "www.bloggingforlogging.com"
UPLOAD_RE = re.compile(r"https?://(?:i\d\.wp\.com/)?(?:www\.)?bloggingforlogging\.com/wp-content/uploads/([^\"'?\s)]+)(?:\?[^\"'\s)]*)?")

media = json.loads((RAW / "media.json").read_text())
known_uploads = {m["source_url"].split("/wp-content/uploads/", 1)[1] for m in media}
categories = {c["id"]: c["name"] for c in json.loads((RAW / "categories.json").read_text())}
tags = {t["id"]: t["name"] for t in json.loads((RAW / "tags.json").read_text())}
needed_uploads = set()


def upload_path(rel: str) -> str:
    """Map an uploads path (possibly a resized variant) to the original file."""
    rel = urllib.parse.unquote(rel)
    if rel not in known_uploads:
        orig = re.sub(r"-\d+x\d+(\.\w+)$", r"\1", rel)
        if orig in known_uploads:
            rel = orig
    needed_uploads.add(rel)
    return f"/assets/images/{rel}"


def fix_images(content: str) -> str:
    # Caption blocks -> image followed by an italic caption paragraph.
    def caption(m):
        inner = m.group(1)
        cap = re.search(r'<p[^>]*class="wp-caption-text"[^>]*>(.*?)</p>', inner, re.S)
        inner = re.sub(r'<p[^>]*class="wp-caption-text".*?</p>', "", inner, flags=re.S)
        out = f"<p>{inner.strip()}</p>"
        if cap and cap.group(1).strip():
            out += f"<p><em>{cap.group(1).strip()}</em></p>"
        return out

    content = re.sub(r'<div[^>]*class="wp-caption[^"]*"[^>]*>(.*?)</div>', caption, content, flags=re.S)

    # Strip img tags down to src + alt so pandoc emits plain markdown images.
    def img(m):
        tag = m.group(0)
        src = re.search(r'\ssrc="([^"]+)"', tag).group(1)
        alt = re.search(r'\salt="([^"]*)"', tag)
        alt = alt.group(1) if alt else ""
        um = UPLOAD_RE.match(html.unescape(src))
        if um:
            src = upload_path(um.group(1))
        return f'<img src="{src}" alt="{alt}">'

    content = re.sub(r"<img\b[^>]*>", img, content)
    # Any remaining links to uploads (e.g. click-to-enlarge anchors).
    content = UPLOAD_RE.sub(lambda m: upload_path(m.group(1)), content)
    return content


def fix_code(content: str) -> str:
    # EnlighterJS blocks -> <pre><code class="language-x">.
    def enlighter(m):
        lang = m.group(1).lower()
        cls = f' class="language-{lang}"' if lang and lang not in ("null", "generic") else ""
        return f"<pre><code{cls}>{m.group(2)}</code></pre>"

    content = re.sub(
        r'<pre class="EnlighterJSRAW" data-enlighter-language="([^"]*)">(.*?)</pre>', enlighter, content, flags=re.S
    )

    # <code class="bash"> -> <code class="language-bash">, lower-cased.
    def lang(m):
        name = m.group(1).lower().removeprefix("language-")
        return f'<pre><code class="language-{name}">'

    content = re.sub(r'<pre><code class="([^"]+)">', lang, content)
    # pandoc writes class-less blocks as indented code; tag them so they get fenced.
    return content.replace("<pre><code>", '<pre><code class="language-nolang">')


def fix_links(content: str) -> str:
    # Make links to other posts on this blog site-relative.
    return re.sub(rf"https?://{re.escape(SITE_HOST)}(/\d{{4}}/\d{{2}}/\d{{2}}/[^\"'#\s]*)", r"\1", content)


def to_markdown(content: str) -> str:
    content = fix_links(fix_images(fix_code(content)))
    md = subprocess.run(
        ["pandoc", "-f", "html", "-t", "gfm", "--wrap=none"],
        input=content,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # pandoc emits ``` powershell for some inputs; normalise.
    md = re.sub(r"^``` (\S+)$", r"```\1", md, flags=re.M)
    md = re.sub(r"^```nolang$", "```", md, flags=re.M)
    return md.strip() + "\n"


def yaml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def front_matter(fields: dict) -> str:
    lines = ["---"]
    for k, v in fields.items():
        if v is None:
            continue
        if isinstance(v, list):
            lines.append(f"{k}: [{', '.join(yaml_str(x) for x in v)}]")
        else:
            lines.append(f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def protect_liquid(md: str) -> str:
    if "{{" in md or "{%" in md:
        return "{% raw %}\n" + md + "{% endraw %}\n"
    return md


def main():
    (OUT / "_posts").mkdir(parents=True, exist_ok=True)

    for p in json.loads((RAW / "posts.json").read_text()):
        date = p["date_gmt"].replace("T", " ") + " +0000"
        title = html.unescape(p["title"]["rendered"])
        permalink = urllib.parse.urlparse(p["link"]).path
        excerpt = re.sub(r'<span class="more">.*?</span>', "", p["excerpt"]["rendered"], flags=re.S)
        excerpt = html.unescape(re.sub(r"<[^>]+>", "", excerpt)).strip()
        fm = {
            "layout": "post",
            "title": yaml_str(title),
            "date": date,
            "permalink": permalink,
            "categories": [categories[c] for c in p["categories"] if categories[c] != "Uncategorized"],
            "tags": [tags[t] for t in p["tags"]] or None,
            "description": yaml_str(excerpt),
        }
        body = protect_liquid(to_markdown(p["content"]["rendered"]))
        name = f"{p['date'][:10]}-{p['slug']}.md"
        (OUT / "_posts" / name).write_text(front_matter(fm) + body)
        print("post", name)

    for p in json.loads((RAW / "pages.json").read_text()):
        if p["slug"] != "sample-page":
            continue
        fm = {"layout": "page", "title": yaml_str("About"), "permalink": "/about/"}
        body = protect_liquid(to_markdown(p["content"]["rendered"]))
        (OUT / "about.md").write_text(front_matter(fm) + body)
        print("page about.md")

    for rel in sorted(needed_uploads):
        dest = OUT / "assets" / "images" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue
        url = f"https://{SITE_HOST}/wp-content/uploads/{urllib.parse.quote(rel)}"
        try:
            with urllib.request.urlopen(url) as r:
                dest.write_bytes(r.read())
            print("image", rel)
        except Exception as e:
            print("FAILED image", rel, e, file=sys.stderr)


if __name__ == "__main__":
    main()
