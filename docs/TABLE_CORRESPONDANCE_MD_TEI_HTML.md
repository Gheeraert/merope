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
| **Encadré Mérope** : div Pandoc réservé `:::: {.merope-encadre}` (titre facultatif dans `::: {.merope-encadre-titre}`) | `floatingText` › `body` › `div type="section1"` (`head` = titre) | `aside.encadre` (titre : `div.encadre-titre`) | structure **native** TEI Commons Publishing (documentation d’usage OpenEdition, section « Encadré », `//floatingText/body`), et non une extension locale du schéma : le schéma embarqué n’est pas modifié et valide la sortie |

## Notes
La TEI conserve une note unique.
Le rendu HTML prévoit deux volets :
- une amorce marginale (désactivée pour le moment, voir `docs/ROADMAP.md` § V1.1)
- une note complète en fin d'article (seule effectivement produite actuellement)

## Encadré Mérope

```
Encadré Mérope
  → syntaxe Markdown réservée
  → TEI <floatingText><body><div type="section1">…
  → HTML <aside class="encadre">…
```

Exemple :

```markdown
:::: {.merope-encadre}
::: {.merope-encadre-titre}
À *retenir*
:::

Premier paragraphe.

Deuxième paragraphe.
::::
```

devient, après le pipeline Pandoc + post-traitement :

```xml
<floatingText>
  <body>
    <div type="section1">
      <head>À <hi rendition="simple:italic">retenir</hi></head>
      <p>Premier paragraphe.</p>
      <p>Deuxième paragraphe.</p>
    </div>
  </body>
</floatingText>
```

puis, côté XSLT :

```html
<aside class="encadre">
  <div class="encadre-titre">À <em>retenir</em></div>
  <p>Premier paragraphe.</p>
  <p>Deuxième paragraphe.</p>
</aside>
```

Points de conception :

- **Pandoc seul ne convient pas** : son écrivain TEI supprime la classe et l’enveloppe d’un `div` fencé, et transforme un titre interne en section qui absorbe la suite. Un filtre Lua (`resources/pandoc/merope_encadre.lua`, ajouté à la commande de `pandoc_converter.py`) réécrit donc le div réservé en `floatingText` *avant* l’écrivain TEI. Un titre `#` écrit à la main dans un encadré est **refusé** (la conversion échoue avec un message explicite) plutôt qu’aplati.
- **Le titre n’est pas un titre Markdown** : il vit dans un `div` imbriqué, donc `extract_heading_levels()` ne le voit jamais et les niveaux `section2`/`section3`… du corps du document restent exacts ; `apply_heading_levels_in_tei_xml` ignore en outre tout `div` situé sous un `floatingText`.
- **Un seul `<h1>`** : le titre d’encadré devient `div.encadre-titre`, jamais un élément de titrage HTML.
- **Présentation** (bordure 1 px, marges latérales de 8 %, marge intérieure, titre centré) : uniquement dans `site.css` (`.encadre`, `.encadre-titre`, repli mobile), rien dans la TEI ni dans le modèle.
- **Contenu accepté** dans un encadré (V1) : paragraphes, citations, listes et formats inline, notes comprises. Images, tableaux, titres, blocs bruts et encadrés imbriqués ne sont pas pris en charge : un encadré qui en contient est conservé tel quel en source (`VERBATIM`), jamais aplati.
- Un div fencé étranger, un encadré non fermé ou mal formé n’est **jamais deviné** : il reste `VERBATIM`, réécrit à l’identique.
