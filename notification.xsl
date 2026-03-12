<xsl:stylesheet version="1.0"
xmlns:xsl="http://www.w3.org/1999/XSL/Transform">

<xsl:output method="html" encoding="UTF-8" indent="yes"/>

<xsl:template match="/notification">

<html>
<head>
<style>

body{
font-family:"MS Mincho","Hiragino Mincho ProN",serif;
line-height:1;
width:100%;
margin:0;
pedding:0}

/* 記 */
.marker{
text-align:center;
}

/* 題（ぶら下げ＋○） */
.notificationtitle{
padding-left:3em;
text-indent:0em;
}

.notificationtitle::before{
content:"〇";
}

/* 発出日 */
.date{text-align:right}


/* 発機関 */
.institution{text-align:right}

/* あて通知 */
.atetsuchi{text-align:right}

.right-align {
  text-align: right;
}

/* 前文 */
.paragraph{
text-align:left;
text-indent:1em;
}

/* 階層ごとのインデント */

.level0 .subtitle{
margin-left:1em;
text-indent:-1em;
}

.level0 .content{
margin-left:1em;
text-indent:1em;
}

.level1 .subtitle{
margin-left:2em;
text-indent:-1em;
}

.level1 .content{
margin-left:2em;
text-indent:1em;
}

.level2 .subtitle{
margin-left:3em;
text-indent:-1em;
}

.level2 .content{
margin-left:3em;
text-indent:1em;
}

.level3 .subtitle{
margin-left:4em;
text-indent:-1em;
}

.level3 .content{
margin-left:4em;
text-indent:1em;
}

.level4 .subtitle{
margin-left:5em;
text-indent:-1em;
}

.level4 .content{
margin-left:5em;
text-indent:1em;
}

.level5 .subtitle{
margin-left:6em;
text-indent:-1em;
}

.level5 .content{
margin-left:6em;
text-indent:1em;
}



</style>

</head>










<body>
<div class="notificationtitle">
<xsl:value-of select="notificationtitle"/>
</div>

<div class="date">
(<xsl:value-of select="date"/>)
</div>

<div class="institution">
(<xsl:value-of select="department"/>)
</div>

<div class="right-align">
  ●(<xsl:choose>
    <xsl:when test="recipient"><xsl:value-of select="recipient"/>あて</xsl:when><!-- recipient がない場合は何も表示しない --></xsl:choose><xsl:value-of select="source"/>通知)
</div>




<xsl:for-each select="body/paragraph">
<div class="paragraph">
<xsl:value-of select="."/>
</div>
</xsl:for-each>



<div class="marker">
<xsl:value-of select="body/marker"/>
</div>

<xsl:apply-templates select="body/section"/>

</body>

</html>

</xsl:template>

<xsl:template match="section">

<div class="level{ @level }">

<div class="subtitle">
<xsl:value-of select="subtitle"/>
</div>

<div class="content">
<xsl:value-of select="content"/>
</div>

<xsl:apply-templates select="section"/>

</div>

</xsl:template>

</xsl:stylesheet>