<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:tei="http://www.tei-c.org/ns/1.0"
  exclude-result-prefixes="tei">

  <xsl:output method="html" encoding="UTF-8" indent="yes"/>
  <xsl:strip-space elements="*"/>

  <xsl:template match="/">
    <xsl:apply-templates select="tei:TEI"/>
  </xsl:template>

  <xsl:template match="tei:TEI">
    <article class="tei-fragment">
      <xsl:apply-templates select="tei:text/tei:body"/>
    </article>
  </xsl:template>

  <xsl:template match="tei:teiHeader"/>

  <xsl:template match="tei:body">
    <xsl:apply-templates/>
    <xsl:if test=".//tei:note">
      <section class="endnotes" id="endnotes">
        <h2>Notes</h2>
        <ol>
          <xsl:for-each select=".//tei:note">
            <xsl:variable name="noteNumber">
              <xsl:number level="any" count="tei:note"/>
            </xsl:variable>
            <li id="note-{$noteNumber}">
              <xsl:apply-templates select="node()" mode="note-body"/>
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

  <xsl:template match="tei:p">
    <p><xsl:apply-templates/></p>
  </xsl:template>

  <xsl:template match="tei:lb">
    <br/>
  </xsl:template>

  <xsl:template match="tei:hi[@rend='italic']">
    <em><xsl:apply-templates/></em>
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

  <xsl:template match="tei:note">
    <xsl:variable name="noteNumber">
      <xsl:number level="any" count="tei:note"/>
    </xsl:variable>
    <sup class="note-call" id="note-call-{$noteNumber}">
      <a href="#note-{$noteNumber}"><xsl:value-of select="$noteNumber"/></a>
    </sup>
  </xsl:template>

  <xsl:template match="tei:figure">
    <figure class="article-figure">
      <xsl:apply-templates select="tei:graphic"/>
      <xsl:variable name="caption" select="(tei:figDesc | tei:head)[1]"/>
      <xsl:if test="$caption">
        <figcaption><xsl:apply-templates select="$caption/node()"/></figcaption>
      </xsl:if>
    </figure>
  </xsl:template>

  <xsl:template match="tei:graphic[@url]">
    <img src="{normalize-space(@url)}">
      <xsl:attribute name="alt">
        <xsl:value-of select="normalize-space((../tei:figDesc | ../tei:head)[1])"/>
      </xsl:attribute>
    </img>
  </xsl:template>

  <xsl:template match="tei:table">
    <table><xsl:apply-templates/></table>
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

  <xsl:template match="tei:hi[@rend='italic']" mode="note-body">
    <em><xsl:apply-templates mode="note-body"/></em>
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

  <xsl:template match="tei:*" mode="note-body">
    <xsl:apply-templates mode="note-body"/>
  </xsl:template>

</xsl:stylesheet>
