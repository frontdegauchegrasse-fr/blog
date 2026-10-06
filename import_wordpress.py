#!/usr/bin/env python3
"""Importe les articles publiés d'un export WordPress (fichier .xml obtenu via
Outils > Exporter sur WordPress.com) en conservant les mêmes adresses
(/AAAA/MM/JJ/slug/), pour que les anciens liens restent valides.

    python3 import_wordpress.py export.xml                 # images laissées sur wordpress.com
    python3 import_wordpress.py export.xml --images        # images rapatriées localement
"""
import argparse
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import html2text

from blogcore import MORE, TZ, Post, slugify, write_post

NS = {"wp": "http://wordpress.org/export/1.2/",
      "content": "http://purl.org/rss/1.0/modules/content/"}
IMG_URL = re.compile(r"https?://[^\s)\"']+/wp-content/uploads/[^\s)\"'?]+(?:\?[^\s)\"']*)?")


def convert(html):
    html = html.replace("<!--more-->", "\n\nZZMOREZZ\n\n")
    html = re.sub(r"\[/?embed\]", "\n", html)          # [embed]url[/embed]
    html = re.sub(r"\[caption[^\]]*\](.*?)\[/caption\]", r"\1", html, flags=re.S)
    if "<p" not in html:                                  # ancien format sans <p>
        html = "".join(f"<p>{b}</p>" for b in re.split(r"\n\s*\n", html))
    h = html2text.HTML2Text()
    h.body_width = 0
    h.unicode_snob = True
    md = h.handle(html).replace("ZZMOREZZ", MORE)
    return re.sub(r"\n{3,}", "\n\n", md).strip()


def fetch_images(post):
    files, n = {}, 0
    def repl(m):
        nonlocal n
        url = m.group(0)
        clean = url.split("?")[0]
        name = slugify(urllib.parse.unquote(clean.rsplit("/", 1)[-1].rsplit(".", 1)[0]), 50) \
            + "." + clean.rsplit(".", 1)[-1].lower()
        try:
            with urllib.request.urlopen(clean, timeout=30) as r:
                files[name] = r.read()
            n += 1
            return post.url + name
        except Exception as e:
            print(f"  image non récupérée : {clean} ({e})", file=sys.stderr)
            return url
    post.body = IMG_URL.sub(repl, post.body)
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--images", action="store_true", help="télécharger les images")
    args = ap.parse_args()

    root = ET.parse(args.export).getroot()
    count = 0
    for item in root.iter("item"):
        if item.findtext("wp:post_type", namespaces=NS) != "post" \
                or item.findtext("wp:status", namespaces=NS) != "publish":
            continue
        title = item.findtext("title") or "Sans titre"
        date = datetime.strptime(item.findtext("wp:post_date", namespaces=NS),
                                 "%Y-%m-%d %H:%M:%S").replace(tzinfo=TZ)
        slug = urllib.parse.unquote(item.findtext("wp:post_name", namespaces=NS) or "") \
            or slugify(title)
        body = convert(item.findtext("content:encoded", namespaces=NS) or "")
        post = Post(title=title, date=date, slug=slug, body=body)
        files = fetch_images(post) if args.images else {}
        write_post(post, files)
        count += 1
        print(f"{date:%Y-%m-%d}  {title}")
    print(f"\n{count} articles importés. Lancez : python3 build.py")


if __name__ == "__main__":
    main()
