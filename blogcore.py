"""Fonctions communes : configuration, format des articles, slugs, dates."""
import os
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content" / "posts"
PUBLIC = ROOT / "public"
TZ = ZoneInfo("Europe/Paris")
MORE = "<!--more-->"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def load_config():
    with open(ROOT / "config.toml", "rb") as f:
        cfg = tomllib.load(f)
    # Les informations sensibles viennent des secrets GitHub (variables d'environnement)
    mail, smtp, env = cfg.setdefault("mail", {}), cfg.setdefault("smtp", {}), os.environ
    for key, var in (("imap_host", "IMAP_HOST"), ("user", "MAIL_USER"),
                     ("password", "MAIL_PASSWORD"), ("secret", "MAIL_SECRET")):
        if env.get(var):
            mail[key] = env[var]
    if env.get("ALLOWED_SENDERS"):
        mail["allowed_senders"] = [a.strip() for a in env["ALLOWED_SENDERS"].split(",") if a.strip()]
    smtp.setdefault("user", mail.get("user", ""))
    if env.get("SMTP_PASSWORD"):
        smtp["password"] = env["SMTP_PASSWORD"]
    cfg["site"]["base_path"] = urlparse(cfg["site"]["base_url"]).path.rstrip("/")
    return cfg


def slugify(text, maxlen=80):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:maxlen].rstrip("-") or "article"


def date_fr(d: datetime):
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


@dataclass
class Post:
    title: str
    date: datetime
    slug: str
    body: str                      # Markdown
    folder: Path | None = None     # dossier source
    extra: dict = field(default_factory=dict)

    @property
    def url(self):
        return f"/{self.date:%Y/%m/%d}/{self.slug}/"

    @property
    def dirname(self):
        return f"{self.date:%Y-%m-%d}-{self.slug}"


def write_post(post: Post, attachments: dict[str, bytes] | None = None) -> Path:
    """Écrit content/posts/AAAA-MM-JJ-slug/index.md (+ fichiers joints).
    Si le dossier existe déjà (même titre, même jour), il est remplacé :
    renvoyer un mail avec le même titre le même jour = correction."""
    folder = CONTENT / post.dirname
    if folder.exists():
        for p in folder.iterdir():
            p.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    head = [
        "---",
        f"title: {post.title}",
        f"date: {post.date.isoformat(timespec='minutes')}",
        f"slug: {post.slug}",
    ]
    head += [f"{k}: {v}" for k, v in post.extra.items()]
    head.append("---")
    (folder / "index.md").write_text("\n".join(head) + "\n\n" + post.body.strip() + "\n",
                                     encoding="utf-8")
    for name, data in (attachments or {}).items():
        (folder / name).write_bytes(data)
    return folder


def read_post(folder: Path) -> Post:
    text = (folder / "index.md").read_text(encoding="utf-8")
    meta, body = {}, text
    if text.startswith("---"):
        _, head, body = text.split("---", 2)
        for line in head.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    date = datetime.fromisoformat(meta.pop("date"))
    if date.tzinfo is None:
        date = date.replace(tzinfo=TZ)
    return Post(title=meta.pop("title"), date=date, slug=meta.pop("slug"),
                body=body.strip(), folder=folder, extra=meta)


def all_posts():
    posts = [read_post(d) for d in CONTENT.iterdir() if (d / "index.md").exists()] \
        if CONTENT.exists() else []
    return sorted(posts, key=lambda p: p.date, reverse=True)
