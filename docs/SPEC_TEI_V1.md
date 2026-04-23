# Spécification TEI V1

## Principe

La TEI cible V1 est une **TEI de publication légère**, intermédiaire entre le Markdown source et le HTML final.

Elle doit être :
- simple à produire
- simple à relire
- simple à transformer en HTML
- assez stable pour des évolutions futures

## Sous-ensemble retenu

- `TEI`
- `teiHeader`
- `fileDesc`
- `titleStmt`
- `publicationStmt`
- `sourceDesc`
- `text`
- `body`
- `div`
- `head`
- `p`
- `list`
- `item`
- `ref`
- `hi`
- `note`
- `figure`
- `graphic`
- `table`
- `row`
- `cell`
- `quote`

## Principes de balisage

### Hiérarchie
Les titres Markdown deviennent des `div` imbriqués contenant `head`.

### Typographie
- italique → `hi rend="italic"`
- gras → `hi rend="bold"`
- petites capitales → `hi rend="smallcaps"` si gérées plus tard

### Liens
- `ref target="..."`

### Notes
- note unique en TEI
- le double rendu (marge + bas de page) relève du HTML, pas du balisage TEI

### Images
- `figure`
- `graphic url="..."`

### Tableaux
- `table`
- `row`
- `cell`
- seulement tableaux simples en V1

## Exemple minimal

```xml
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title>Exemple</title>
      </titleStmt>
      <publicationStmt>
        <p>Publication statique locale</p>
      </publicationStmt>
      <sourceDesc>
        <p>Source Markdown exportée depuis Google Docs.</p>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
  <text>
    <body>
      <div>
        <head>Titre</head>
        <p>Un paragraphe avec une <note>note d’exemple.</note></p>
      </div>
    </body>
  </text>
</TEI>
```
