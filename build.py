#!/usr/bin/env python3
"""Génère le site statique dans public/ à partir de content/posts/."""
import re
import shutil
from datetime import datetime
from email.utils import format_datetime
from xml.sax.saxutils import escape

import markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from blogcore import MORE, PUBLIC, ROOT, all_posts, date_fr, load_config

YOUTUBE = re.compile(
    r"^\s*<?https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)"
    r"([\w-]{11})\S*?>?\s*$", re.M)


def to_html(md_text, prefix=""):
    md_text = YOUTUBE.sub(
        lambda m: f'\n<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{m.group(1)}" '
                  f'title="Vidéo YouTube" allowfullscreen loading="lazy"></iframe></div>\n',
        md_text)
    html = markdown.markdown(md_text, extensions=["extra", "sane_lists", "nl2br"])
    if prefix:  # adresse du site (sous-dossier GitHub Pages, ou complète pour le RSS)
        html = re.sub(r'(src|href)="/(?!/)', rf'\1="{prefix}/', html)
    return html


def build():
    cfg = load_config()
    site = cfg["site"]
    env = Environment(loader=FileSystemLoader(ROOT / "templates"),
                      autoescape=select_autoescape(["html"]))
    env.filters["date_fr"] = date_fr
    bp = site["base_path"]
    env.filters["u"] = lambda path: bp + path   # préfixe les liens internes

    posts = all_posts()
    for p in posts:
        full = p.body.replace(MORE, "")
        p.html = to_html(full, bp)
        p.has_more = MORE in p.body
        p.excerpt_html = to_html(p.body.split(MORE)[0], bp) if p.has_more else p.html

    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir()
    shutil.copytree(ROOT / "static", PUBLIC / "static")

    common = dict(site=site, recent=posts[:5], year=datetime.now().year)

    def render(template, path, **ctx):
        out = PUBLIC / path.strip("/") / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(env.get_template(template).render(**common, **ctx), encoding="utf-8")

    # Accueil + pagination
    per = site.get("posts_per_page", 10)
    pages = [posts[i:i + per] for i in range(0, len(posts), per)] or [[]]
    for n, chunk in enumerate(pages, 1):
        render("index.html", "/" if n == 1 else f"/page/{n}/",
               posts=chunk, page=n, pages=len(pages))

    # Articles (+ copie des images et pièces jointes)
    for i, p in enumerate(posts):
        render("post.html", p.url, post=p,
               newer=posts[i - 1] if i > 0 else None,
               older=posts[i + 1] if i + 1 < len(posts) else None)
        for f in p.folder.iterdir():
            if f.name != "index.md":
                shutil.copy2(f, PUBLIC / p.url.strip("/") / f.name)

    render("archives.html", "/archives/", posts=posts)
    (PUBLIC / "404.html").write_text(env.get_template("404.html").render(**common), encoding="utf-8")

    # Flux RSS (même adresse que WordPress : /feed/)
    base = site["base_url"].rstrip("/")
    items = "".join(
        f"<item><title>{escape(p.title)}</title><link>{base}{p.url}</link>"
        f"<guid>{base}{p.url}</guid><pubDate>{format_datetime(p.date)}</pubDate>"
        f"<description>{escape(to_html(p.body.replace(MORE, ''), base))}</description></item>"
        for p in posts[:20])
    feed = (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f"<title>{escape(site['title'])}</title><link>{base}/</link>"
            f"<description>{escape(site.get('tagline', ''))}</description>"
            f"<language>{site.get('language', 'fr')}</language>{items}</channel></rss>")
    (PUBLIC / "feed").mkdir(exist_ok=True)
    (PUBLIC / "feed" / "index.xml").write_text(feed, encoding="utf-8")

    print(f"Site généré : {len(posts)} articles dans {PUBLIC}")


if __name__ == "__main__":
    build()
