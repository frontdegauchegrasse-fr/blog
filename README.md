# Blog statique alimenté par mail, hébergé sur GitHub

Remplace le blog WordPress « Front de gauche – Pays Grassois ».
On écrit un mail, il devient un article. Toutes les 10 minutes, GitHub relève la boîte,
enregistre les nouveaux articles dans le dépôt et met le site à jour sur GitHub Pages.
Aucun serveur à entretenir, aucune base de données, aucune interface d'administration.

## Publier

Envoyer un mail **depuis une adresse autorisée** à `blog+CODE@votre-domaine`
(ou à `blog@votre-domaine` avec le CODE au début de l'objet).

| Dans le mail | Résultat |
|---|---|
| Objet | Titre de l'article |
| Corps (gras, italique, liens) | Texte de l'article, mise en forme conservée |
| Ligne `--suite--` | Coupe l'article en page d'accueil : lien « (suite…) » |
| Ligne contenant seulement un lien YouTube | Vidéo intégrée |
| Photo jointe | Placée en tête de l'article (ou à sa place si insérée dans le texte) |
| PDF joint | Lien de téléchargement en bas de l'article |
| Tout ce qui suit `-- ` | Signature, ignorée |
| Même titre renvoyé le même jour | Remplace l'article (correction) |
| Objet `SUPPRIMER adresse-de-l-article` | Retire l'article |

Délai : en général 10 à 20 minutes (GitHub décale parfois les tâches planifiées).
Pour publier tout de suite : onglet **Actions** > **Publier** > **Run workflow**.

## Mise en place

### 1. Le dépôt

1. Créer un dépôt **public** sur GitHub (ex. `blog`) — GitHub Pages est gratuit pour les dépôts publics.
2. Y envoyer le contenu de ce dossier :
   ```bash
   cd blog-fdg
   git init -b main && git add . && git commit -m "Blog"
   git remote add origin git@github.com:IDENTIFIANT/blog.git
   git push -u origin main
   ```
3. **Settings > Pages** : Source = **GitHub Actions**.

### 2. La configuration

Dans `config.toml` (public, donc sans mot de passe) : renseigner `base_url`,
par exemple `https://identifiant.github.io/blog`.

**Bandeau** : enregistrer l'image de têtière du blog WordPress sous `static/tetiere.jpg`.

### 3. La boîte mail (secrets)

Créer une adresse dédiée avec accès IMAP (ex. `blog@…`), puis dans
**Settings > Secrets and variables > Actions > New repository secret** :

| Secret | Exemple |
|---|---|
| `IMAP_HOST` | `imap.exemple.fr` |
| `MAIL_USER` | `blog@exemple.fr` |
| `MAIL_PASSWORD` | mot de passe (ou mot de passe d'application) |
| `MAIL_SECRET` | un code à vous, ex. `rouge-7f3k` |
| `ALLOWED_SENDERS` | `frederic@exemple.fr, autre@exemple.fr` |
| `SMTP_PASSWORD` | facultatif, pour l'accusé de réception (`[smtp]` dans config.toml) |

L'adresse d'expéditeur se falsifie facilement : c'est le code qui protège vraiment le blog.

Si les dossiers « Publies » / « Refuses » ne se créent pas, certains serveurs
exigent le préfixe : mettre `INBOX.Publies` et `INBOX.Refuses` dans `config.toml`.

### 4. Reprendre les anciens articles (une fois, sur votre ordinateur)

Sur WordPress.com : Outils > Exporter > Exporter tout, puis :

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python import_wordpress.py export.xml --images
git add content && git commit -m "Import WordPress" && git push
```

Les adresses des articles gardent la forme WordPress (`/2025/10/28/titre/`).

### 5. Nom de domaine (facultatif)

**Settings > Pages > Custom domain**, puis chez le registraire un enregistrement
`CNAME` vers `identifiant.github.io`. Mettre ensuite `base_url` à jour dans `config.toml`.
Avec un domaine, les anciens liens `/2025/10/28/titre/` restent identiques à ceux de WordPress.

## Bon à savoir

- Le dépôt étant public, ses journaux d'Actions le sont aussi : le script n'y écrit
  jamais l'adresse ni l'objet des mails refusés. Les secrets sont masqués par GitHub.
- GitHub suspend les tâches planifiées d'un dépôt public inactif pendant 60 jours ;
  le workflow fait un commit vide au bout de 45 jours sans publication pour l'éviter.
- Le dossier `content/posts/` (un dossier par article : `index.md` + images) est la
  sauvegarde complète du blog, versionnée. On peut aussi modifier un article
  directement sur github.com (crayon ✏️) : le site se met à jour seul.

## Tester sur son ordinateur

```bash
.venv/bin/python mail2post.py --eml un-mail.eml    # sans toucher à la boîte
.venv/bin/python build.py
cd public && python3 -m http.server 8000           # http://localhost:8000
```

(Avec `base_url` en sous-dossier, servir plutôt le dossier parent : voir la ligne
`base_url` de config.toml, ou la mettre temporairement à `http://localhost:8000`.)
Dans Mail sur Mac : Fichier > Enregistrer sous… > « Source brute » donne un .eml.

## Fichiers

- `.github/workflows/publier.yml` : relève, enregistre, génère, met en ligne
- `mail2post.py` : transforme les mails en articles
- `build.py` : génère le site (accueil paginé, articles, archives, RSS, page 404)
- `import_wordpress.py` : reprise des anciens articles
- `templates/`, `static/style.css` : apparence (couleurs en tête de la feuille de style)
