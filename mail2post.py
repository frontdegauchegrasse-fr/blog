#!/usr/bin/env python3
"""Relève la boîte mail du blog et transforme chaque mail autorisé en article
(dans content/posts/). Lancé par GitHub Actions, qui enregistre ensuite les
nouveaux articles dans le dépôt et met le site en ligne.

    python3 mail2post.py              # relève la boîte IMAP
    python3 mail2post.py --eml x.eml  # teste sur un mail enregistré (sans IMAP)

Dans le mail :
  - l'objet devient le titre ;
  - une ligne « --suite-- » coupe le texte affiché en page d'accueil ;
  - une ligne contenant seulement un lien YouTube devient une vidéo ;
  - les photos jointes sont placées en tête (ou à leur place si insérées
    dans le corps du mail), les PDF sont proposés en téléchargement ;
  - tout ce qui suit la signature (« -- ») est ignoré.
  - objet « SUPPRIMER <adresse ou slug de l'article> » : retire l'article.
"""
import argparse
import email
import imaplib
import io
import os
import re
import shutil
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from email.policy import default as policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

import html2text

from blogcore import MORE, TZ, Post, all_posts, load_config, slugify, write_post

IMAGE_MAX = 1600  # px, côté le plus long


# ---------------------------------------------------------------- contrôle
def check_auth(msg, cfg):
    """Renvoie (ok, objet_nettoyé)."""
    sender = parseaddr(msg.get("From", ""))[1].lower()
    allowed = [a.lower() for a in cfg["allowed_senders"]]
    subject = str(msg.get("Subject", "")).strip()
    if sender not in allowed:
        return False, subject
    secret = cfg.get("secret", "")
    if not secret:
        return True, subject
    recipients = getaddresses(msg.get_all("To", []) + msg.get_all("Delivered-To", [])
                              + msg.get_all("X-Original-To", []))
    if any(f"+{secret.lower()}@" in addr.lower() for _, addr in recipients):
        return True, subject
    if subject.lower().startswith(secret.lower()):
        return True, subject[len(secret):].lstrip(" :-–")
    return False, subject


# ---------------------------------------------------------------- contenu
def safe_name(filename, used):
    stem, _, ext = (filename or "fichier").rpartition(".")
    name = f"{slugify(stem or 'fichier', 50)}.{slugify(ext, 5)}" if stem else slugify(filename, 50)
    base, n = name, 2
    while name in used:
        name = re.sub(r"(\.[^.]+)?$", rf"-{n}\1", base, count=1)
        n += 1
    used.add(name)
    return name


def shrink_image(data):
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        if max(img.size) <= IMAGE_MAX and len(data) < 800_000:
            return data
        img.thumbnail((IMAGE_MAX, IMAGE_MAX))
        out = io.BytesIO()
        fmt = img.format or "JPEG"
        if fmt == "JPEG" and img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.save(out, format=fmt if fmt in ("JPEG", "PNG", "WEBP") else "JPEG", quality=85)
        return out.getvalue()
    except Exception:
        return data


def clean_body(text):
    text = text.replace("\r\n", "\n")
    # signature
    text = re.split(r"^\\?-\\?- ?$", text, maxsplit=1, flags=re.M)[0]
    # « Envoyé de mon iPhone » & co
    text = re.sub(r"^(Envoyé de mon .*|Sent from my .*)$", "", text, flags=re.M)
    # marqueur de suite
    text = re.sub(r"^\s*\\?-\\?-\s*suite\s*\\?-\\?-\s*$", f"\n{MORE}\n", text, flags=re.M | re.I)
    # espace parasite de html2text avant la ponctuation : « **Hier soir** , »
    text = re.sub(r"(\*\*|_) ([,.])", r"\1\2", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def mail_to_post(msg, title):
    try:
        date = parsedate_to_datetime(msg["Date"]).astimezone(TZ)
    except Exception:
        date = datetime.now(TZ)
    post = Post(title=title.strip() or "Sans titre", date=date,
                slug=slugify(title), body="")

    files, used, cids = {}, set(), {}
    images, docs = [], []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        is_att = part.get_filename() or part.get("Content-ID")
        if not is_att or ctype in ("text/plain", "text/html"):
            continue
        data = part.get_payload(decode=True) or b""
        if ctype.startswith("image/"):
            data = shrink_image(data)
        name = safe_name(part.get_filename() or f"image.{ctype.split('/')[-1]}", used)
        files[name] = data
        cid = (part.get("Content-ID") or "").strip("<> ")
        if cid:
            cids[cid] = name
        (images if ctype.startswith("image/") else docs).append(name)

    body_part = msg.get_body(preferencelist=("html", "plain"))
    raw = body_part.get_content() if body_part else ""
    if body_part and body_part.get_content_type() == "text/html":
        h = html2text.HTML2Text()
        h.body_width = 0
        h.unicode_snob = True
        raw = h.handle(raw)
    body = clean_body(raw)

    placed = set()
    for cid, name in cids.items():
        if f"cid:{cid}" in body:
            body = body.replace(f"cid:{cid}", post.url + name)
            placed.add(name)
    body = re.sub(r"!\[[^\]]*\]\(cid:[^)]*\)", "", body)  # images inline non retrouvées

    top = [f"![]({post.url}{n})" for n in images if n not in placed]
    bottom = [f'<p class="piece-jointe">📎 <a href="{post.url}{n}">{n}</a></p>' for n in docs]
    post.body = "\n\n".join(top + [body] + bottom)
    return post, files


# ---------------------------------------------------------------- actions
def delete_post(ref):
    ref = ref.strip().rstrip("/").split("/")[-1]
    for p in all_posts():
        if p.slug == ref or p.folder.name == ref:
            shutil.rmtree(p.folder)
            return p.title
    return None


def handle(msg, cfg):
    """Traite un mail. Renvoie (statut, message) ; statut ∈ ok / refus / erreur."""
    ok, subject = check_auth(msg, cfg["mail"])
    if not ok:
        return "refus", "expéditeur ou code non autorisé"
    m = re.match(r"^\s*SUPPRIMER\s*:?\s*(\S+)", subject, re.I)
    if m:
        title = delete_post(m.group(1))
        return ("ok", f"Article supprimé : {title}") if title else \
               ("erreur", f"Article introuvable : {m.group(1)}")
    post, files = mail_to_post(msg, subject)
    write_post(post, files)
    url = cfg["site"]["base_url"].rstrip("/") + post.url
    return "ok", f"Publié : {post.title}\n{url}"


def reply(cfg, msg, text):
    s = cfg.get("smtp", {})
    if not s.get("enabled"):
        return
    r = EmailMessage()
    r["From"], r["To"] = s["user"], parseaddr(msg["From"])[1]
    r["Subject"] = "Re: " + str(msg.get("Subject", ""))
    r.set_content(text)
    try:
        with smtplib.SMTP_SSL(s["host"], s.get("port", 465)) as smtp:
            smtp.login(s["user"], s["password"])
            smtp.send_message(r)
    except Exception as e:
        print("Accusé de réception non envoyé :", e, file=sys.stderr)


def fetch_imap(cfg, state):
    m = cfg["mail"]
    if not m.get("imap_host"):
        print("Boîte mail non configurée (secrets IMAP_HOST, MAIL_USER… absents) : rien à relever.")
        return
    imap = imaplib.IMAP4_SSL(m["imap_host"], m.get("imap_port", 993))
    imap.login(m["user"], m["password"])
    for f in (m["done_folder"], m["rejected_folder"]):
        imap.create(f)  # sans effet s'il existe
    imap.select(m.get("folder", "INBOX"))
    _, data = imap.uid("search", None, "ALL")
    for uid in data[0].split():
        _, parts = imap.uid("fetch", uid, "(RFC822)")
        msg = email.message_from_bytes(parts[0][1], policy=policy)
        try:
            status, text = handle(msg, cfg)
        except Exception as e:
            status, text = "erreur", f"Erreur : {e}"
        # Les journaux GitHub Actions d'un dépôt public sont visibles de tous :
        # on n'y écrit ni adresse ni objet des mails refusés.
        print(f"[{status}] " + (text.splitlines()[0] if status != "refus" else "mail refusé"))
        if status != "refus":
            reply(cfg, msg, text)
        if status == "ok":
            state["changed"] = True
        dest = m["rejected_folder"] if status == "refus" else m["done_folder"]
        if imap.uid("copy", uid, dest)[0] == "OK":
            imap.uid("store", uid, "+FLAGS", r"(\Deleted)")
    imap.expunge()
    imap.logout()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eml", help="traiter un fichier .eml au lieu de la boîte IMAP")
    args = ap.parse_args()
    cfg = load_config()
    state = {"changed": False}
    try:
        if args.eml:
            with open(args.eml, "rb") as f:
                msg = email.message_from_binary_file(f, policy=policy)
            status, text = handle(msg, cfg)
            print(f"[{status}] {text}")
            state["changed"] = status == "ok"
        else:
            fetch_imap(cfg, state)
    finally:
        # Signale à GitHub Actions s'il y a du nouveau, même après une erreur,
        # pour que les articles déjà créés soient bien enregistrés.
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"changed={'true' if state['changed'] else 'false'}\n")


if __name__ == "__main__":
    main()
