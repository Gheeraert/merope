# Tableau de correspondance Markdown → TEI → HTML

## Cas pris en charge en V1

| Markdown | TEI cible | HTML cible | Remarques |
|---|---|---|---|
| `# Titre` | `div` + `head` | `section` + titre HTML | hiérarchie stable |
| paragraphe | `p` | `p` | cas standard |
| `*italique*` | `hi rend="italic"` | `em` | |
| `**gras**` | `hi rend="bold"` | `strong` | |
| `[texte](url)` | `ref target="url"` | `a href` | |
| note Markdown | `note` | appel + note finale | |
| liste à puces | `list` + `item` | `ul` / `li` | |
| liste numérotée | `list type="ordered"` | `ol` / `li` | |
| bloc cité | `quote` | `blockquote` | |
| image Markdown | `figure` + `graphic` | `figure` + `img` + lien lightbox | |
| tableau simple | `table` + `row` + `cell` | `table` | |

## Notes
La TEI conserve une note unique.  
Le rendu HTML peut produire :
- une amorce marginale
- une note complète en fin d’article
