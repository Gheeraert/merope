# Roadmap

## V1
- config JSON
- interface Tkinter
- menus éditables
- bannière
- TEI pivot
- XSLT HTML
- images + lightbox
- notes marginales + notes finales
- CLI headless (`bloggen build --config ...`)
- RSS (`feed.xml`), sitemap (`sitemap.xml`, avec `lastmod`), `robots.txt` et méta SEO (Open Graph, Twitter Card, JSON-LD Article/WebSite) — sitemap/RSS si `site.base_url` renseigné
- surcharge de thème (CSS/JS) et de gabarits HTML par projet
- éditeur de contenu WYSIWYG intégré (création/édition de pages et billets sans quitter l'application)
- import Markdown et copier-coller nettoyé depuis Word/Google Docs dans l'éditeur
- exposants et conversion automatique des ordinaux de siècle (« Ier siècle », « XXIe siècle »)
- recherche plein texte statique côté client (index JSON généré au build, sans serveur ni base de données)
- alignement de paragraphe (gauche/centré/droite/justifié) dans l'éditeur, reporté sur le site généré
- sélecteur de page/billet existant pour les liens de menu internes ; les liens externes s'ouvrent intégrés (iframe) en conservant menus et bannière
- sections de premier niveau du menu latéral pouvant pointer directement vers une page/un billet/un site externe, sans sous-menu obligatoire

## V1.1
- amélioration responsive
- raffinement du rendu des notes marginales
- meilleure gestion des images issues de Google Docs
- petite prévisualisation locale intégrée

## V2
- enrichissements TEI supplémentaires
- meilleure automatisation des médias
- pagination réelle de l'archive (`blog.posts_per_page` n'est pas encore branché)
