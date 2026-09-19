# Tableau de correspondance Markdown → TEI → HTML

## Cas pris en charge en V1

| Markdown | TEI cible | HTML cible | Remarques |
|---|---|---|---|
| `# Titre` | `div` + `head` | `section` + titre HTML | hiérarchie stable |
| paragraphe | `p` | `p` | cas standard |
| `*italique*` | `hi rend="italic"` | `em` | |
| `**gras**` | `hi rend="bold"` | `strong` | |
| `[texte]{.underline}` | `hi rend="simple:underline"` | souligné | syntaxe Pandoc pour le soulignement, sans équivalent Markdown natif |
| `~~barré~~` | `hi rend="strikethrough"` | barré | |
| exposant (ex. ordinal de siècle) | `hi rend="superscript"` | `sup` | produit par l’éditeur, pas par une syntaxe Markdown tapée à la main |
| `[texte](url)` | `ref target="url"` | `a href` | seules les destinations de schéma autorisé (`http`, `https`, `mailto`, `tel`) survivent à la publication ; les autres sont retirées, le texte visible est conservé |
| note Markdown (`[^1]`/`^[...]`) ou raccourci `((note))` | `note` | appel + note finale | `((note))` est converti en note avant Pandoc |
| liste à puces | `list` + `item` | `ul` / `li` | |
| liste numérotée | `list type="ordered"` | `ol` / `li` | |
| bloc cité | `quote` | `blockquote` | |
| alignement de paragraphe (gauche/centré/droite/justifié) | attribut de rendu sur `p` | `style`/classe CSS sur `p` | réglé dans l’éditeur, reporté sur le HTML publié |
| image Markdown | `figure` + `graphic` | `figure` + `img` + lien lightbox | légende optionnelle sous l’image |
| tableau simple | `table` + `row` + `cell` | `table` | lignes irrégulières complétées avec des cellules vides à l’export depuis l’éditeur, sans perte de cellule existante |

## Notes
La TEI conserve une note unique.
Le rendu HTML prévoit deux volets :
- une amorce marginale (désactivée pour le moment, voir `docs/ROADMAP.md` § V1.1)
- une note complète en fin d'article (seule effectivement produite actuellement)
