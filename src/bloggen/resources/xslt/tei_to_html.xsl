<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  exclude-result-prefixes="tei">

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>
  <xsl:strip-space elements="*"/>

  <xsl:param name="article_slug" select="'article'"/>
  <xsl:param name="clickable_figures" select="'1'"/>

  <xsl:template match="/">
    <xsl:apply-templates select="tei:TEI"/>
  </xsl:template>

  <xsl:template match="tei:TEI">
    <xsl:variable name="publicationDate" select="normalize-space(string((tei:teiHeader/tei:fileDesc/tei:publicationStmt/tei:date)[1]))"/>
    <article class="tei-fragment article-main" data-article-slug="{$article_slug}">
      <xsl:if test="$publicationDate != ''">
        <header class="article-header">
          <p class="article-meta">
            <time datetime="{$publicationDate}">
              <xsl:value-of select="$publicationDate"/>
            </time>
          </p>
        </header>
      </xsl:if>
      <xsl:apply-templates select="tei:text/tei:body"/>
    </article>
  </xsl:template>

  <xsl:template match="tei:teiHeader"/>

  <xsl:template match="tei:body">
    <xsl:apply-templates/>
    <xsl:if test=".//tei:note">
      <section class="endnotes" id="endnotes">
        <h2>Notes</h2>
        <ol class="endnotes-list">
          <xsl:for-each select=".//tei:note">
            <xsl:variable name="noteNumber">
              <xsl:number level="any" count="tei:note"/>
            </xsl:variable>
            <li id="note-{$noteNumber}" data-note-number="{$noteNumber}">
              <xsl:apply-templates select="node()" mode="note-body"/>
              <a class="note-backref" href="#note-call-{$noteNumber}" aria-label="Retour au texte">↩</a>
            </li>
          </xsl:for-each>
        </ol>
      </section>
    </xsl:if>
  </xsl:template>

  <xsl:template match="tei:div">
    <section class="tei-div">
      <xsl:apply-templates/>
    </section>
  </xsl:template>

  <xsl:template match="tei:div/tei:head">
    <xsl:variable name="level" select="count(ancestor::tei:div)"/>
    <xsl:choose>
      <xsl:when test="$level = 1"><h1><xsl:apply-templates/></h1></xsl:when>
      <xsl:when test="$level = 2"><h2><xsl:apply-templates/></h2></xsl:when>
      <xsl:when test="$level = 3"><h3><xsl:apply-templates/></h3></xsl:when>
      <xsl:when test="$level = 4"><h4><xsl:apply-templates/></h4></xsl:when>
      <xsl:when test="$level = 5"><h5><xsl:apply-templates/></h5></xsl:when>
      <xsl:otherwise><h6><xsl:apply-templates/></h6></xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="tei:head">
    <h2><xsl:apply-templates/></h2>
  </xsl:template>

  <xsl:template match="tei:p">
    <xsl:choose>
      <xsl:when test="count(*) = 1 and tei:figure and normalize-space(.) = normalize-space(tei:figure/tei:head[1])">
        <xsl:apply-templates select="tei:figure"/>
      </xsl:when>
      <xsl:when test="not(*) and preceding-sibling::*[1][self::tei:p[count(*) = 1 and tei:figure]] and normalize-space(.) = normalize-space(preceding-sibling::*[1]/tei:figure/tei:head[1])"/>
      <xsl:otherwise>
        <p><xsl:apply-templates/></p>
      </xsl:otherwise>
    </xsl:choose>
  </xsl:template>

  <xsl:template match="tei:p[count(*) = 1 and tei:figure and not(normalize-space(text()[not(ancestor::tei:figure)]))]">
    <xsl:apply-templates select="tei:figure"/>
  </xsl:template>

  <xsl:template match="tei:p[not(*) and preceding-sibling::*[1][self::tei:p[count(*) = 1 and tei:figure]] and normalize-space(.) = normalize-space(preceding-sibling::*[1]/tei:figure/tei:head[1])]"/>

  <xsl:template match="tei:hi[contains(concat(' ', normalize-space(@rendition), ' '), ' simple:bold ') and contains(concat(' ', normalize-space(@rendition), ' '), ' simple:italic ')]" priority="3">
    <strong><em><xsl:apply-templates/></em></strong>
  </xsl:template>

  <xsl:template match="tei:hi[contains(concat(' ', normalize-space(@rendition), ' '), ' simple:italic ')]">
    <em><xsl:apply-templates/></em>
  </xsl:template>

  <xsl:template match="tei:lb">
    <br/>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='italic']">
    <em><xsl:apply-templates/></em>
  </xsl:template>

  <xsl:template match="tei:hi[contains(concat(' ', normalize-space(@rendition), ' '), ' simple:bold ')]">
    <strong><xsl:apply-templates/></strong>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='bold']">
    <strong><xsl:apply-templates/></strong>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='smallcaps']">
    <span class="smallcaps"><xsl:apply-templates/></span>
  </xsl:template>

  <xsl:template match="tei:ref[@target]">
    <a href="{normalize-space(@target)}"><xsl:apply-templates/></a>
  </xsl:template>

  <xsl:template match="tei:list[@type='ordered']">
    <ol><xsl:apply-templates/></ol>
  </xsl:template>

  <xsl:template match="tei:list">
    <ul><xsl:apply-templates/></ul>
  </xsl:template>

  <xsl:template match="tei:item">
    <li><xsl:apply-templates/></li>
  </xsl:template>

  <xsl:template match="tei:quote">
    <blockquote><xsl:apply-templates/></blockquote>
  </xsl:template>

  <xsl:template match="tei:q">
    <blockquote><xsl:apply-templates/></blockquote>
  </xsl:template>

  <xsl:template match="tei:note">
    <xsl:variable name="noteNumber">
      <xsl:number level="any" count="tei:note"/>
    </xsl:variable>
    <sup class="note-call" id="note-call-{$noteNumber}" data-note-number="{$noteNumber}">
      <a class="note-call-link" href="#note-{$noteNumber}" aria-label="{concat('Voir la note ', $noteNumber)}"><xsl:value-of select="$noteNumber"/></a>
    </sup>
  </xsl:template>

  <xsl:template match="tei:figure">
    <xsl:variable name="url" select="normalize-space((tei:graphic/@url)[1])"/>
    <xsl:variable name="captionText" select="normalize-space(string((tei:figDesc | tei:head)[1]))"/>

    <figure class="article-figure">
      <xsl:if test="$url != ''">
        <xsl:choose>
          <xsl:when test="$clickable_figures = '1'">
            <a class="figure-image-link" href="{$url}" data-article-group="{concat('article-', normalize-space($article_slug))}">
              <img src="{$url}">
                <xsl:attribute name="alt">
                  <xsl:choose>
                    <xsl:when test="$captionText != ''"><xsl:value-of select="$captionText"/></xsl:when>
                    <xsl:otherwise>Illustration</xsl:otherwise>
                  </xsl:choose>
                </xsl:attribute>
              </img>
            </a>
          </xsl:when>
          <xsl:otherwise>
            <img src="{$url}">
              <xsl:attribute name="alt">
                <xsl:choose>
                  <xsl:when test="$captionText != ''"><xsl:value-of select="$captionText"/></xsl:when>
                  <xsl:otherwise>Illustration</xsl:otherwise>
                </xsl:choose>
              </xsl:attribute>
            </img>
          </xsl:otherwise>
        </xsl:choose>
      </xsl:if>

      <xsl:if test="$captionText != ''">
        <figcaption><xsl:value-of select="$captionText"/></figcaption>
      </xsl:if>
    </figure>
  </xsl:template>

  <xsl:template match="tei:table">
    <table class="tei-table"><xsl:apply-templates/></table>
  </xsl:template>

  <xsl:template match="tei:row">
    <tr><xsl:apply-templates/></tr>
  </xsl:template>

  <xsl:template match="tei:cell">
    <td><xsl:apply-templates/></td>
  </xsl:template>

  <xsl:template match="text()">
    <xsl:value-of select="."/>
  </xsl:template>

  <xsl:template match="tei:*">
    <xsl:apply-templates/>
  </xsl:template>

  <xsl:template match="text()" mode="note-body">
    <xsl:value-of select="."/>
  </xsl:template>

  <xsl:template match="tei:lb" mode="note-body">
    <br/>
  </xsl:template>

  <xsl:template match="tei:p" mode="note-body">
    <p><xsl:apply-templates mode="note-body"/></p>
  </xsl:template>

  <xsl:template match="tei:hi[contains(concat(' ', normalize-space(@rendition), ' '), ' simple:bold ') and contains(concat(' ', normalize-space(@rendition), ' '), ' simple:italic ')]" mode="note-body" priority="3">
    <strong><em><xsl:apply-templates mode="note-body"/></em></strong>
  </xsl:template>

  <xsl:template match="tei:hi[contains(concat(' ', normalize-space(@rendition), ' '), ' simple:italic ')]" mode="note-body">
    <em><xsl:apply-templates mode="note-body"/></em>
  </xsl:template>

  <xsl:template match="tei:list[@type='ordered']" mode="note-body">
    <ol><xsl:apply-templates mode="note-body"/></ol>
  </xsl:template>

  <xsl:template match="tei:list" mode="note-body">
    <ul><xsl:apply-templates mode="note-body"/></ul>
  </xsl:template>

  <xsl:template match="tei:item" mode="note-body">
    <li><xsl:apply-templates mode="note-body"/></li>
  </xsl:template>

  <xsl:template match="tei:quote | tei:q" mode="note-body">
    <blockquote><xsl:apply-templates mode="note-body"/></blockquote>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='italic']" mode="note-body">
    <em><xsl:apply-templates mode="note-body"/></em>
  </xsl:template>

  <xsl:template match="tei:hi[contains(concat(' ', normalize-space(@rendition), ' '), ' simple:bold ')]" mode="note-body">
    <strong><xsl:apply-templates mode="note-body"/></strong>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='bold']" mode="note-body">
    <strong><xsl:apply-templates mode="note-body"/></strong>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='smallcaps']" mode="note-body">
    <span class="smallcaps"><xsl:apply-templates mode="note-body"/></span>
  </xsl:template>

  <xsl:template match="tei:ref[@target]" mode="note-body">
    <a href="{normalize-space(@target)}"><xsl:apply-templates mode="note-body"/></a>
  </xsl:template>

  <xsl:template match="tei:table" mode="note-body">
    <table class="tei-table"><xsl:apply-templates mode="note-body"/></table>
  </xsl:template>

  <xsl:template match="tei:row" mode="note-body">
    <tr><xsl:apply-templates mode="note-body"/></tr>
  </xsl:template>

  <xsl:template match="tei:cell" mode="note-body">
    <td><xsl:apply-templates mode="note-body"/></td>
  </xsl:template>

  <xsl:template match="tei:*" mode="note-body">
    <xsl:apply-templates mode="note-body"/>
  </xsl:template>

</xsl:stylesheet>
