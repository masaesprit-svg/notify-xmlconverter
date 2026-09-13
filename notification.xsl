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
padding:0}

/* 記 */
.marker{
text-align:center;
}

/* 題（ぶら下げ＋○） */
/* ::before はWordで無視されるため、〇はXSLTでテキストとして出力する */
.notificationtitle{
margin-left:3em;
text-indent:0em;
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

/* 表（本文と同じフォントにする） */
/* Wordは inherit の解釈が不安定なため、明示的に指定する */
table{
font-family:"MS Mincho","Hiragino Mincho ProN",serif;
}

table p{
font-family:"MS Mincho","Hiragino Mincho ProN",serif;
margin:0;
padding:0;
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
<xsl:text>〇</xsl:text>
<xsl:apply-templates select="notificationtitle"/>
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
<xsl:apply-templates/>
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
<xsl:apply-templates select="subtitle"/>
</div>

<!-- content ごとに div を作る（1つにまとめると段落が分かれない） -->
<xsl:for-each select="content">
<div class="content">
<xsl:apply-templates/>
</div>
</xsl:for-each>

<xsl:apply-templates select="table"/>

<xsl:apply-templates select="section"/>

</div>

</xsl:template>

<!-- 下線 -->
<xsl:template match="underline">
<u><xsl:apply-templates/></u>
</xsl:template>

<!-- ======================================== -->
<!-- 表                                        -->
<!--   Wordが書き出す形式に合わせている          -->
<!--   ・table自体は border:none                -->
<!--   ・罫線は各tdに指定                       -->
<!--   ・2列目以降は border-left:none で二重線を防ぐ -->
<!--   ・幅は列数から自動計算（全体424.65pt）     -->
<!-- ======================================== -->
<xsl:template match="table">
<table class="MsoTableGrid" border="1" cellspacing="0" cellpadding="0"
 style="border-collapse:collapse;border:none">
<xsl:apply-templates select="row"/>
</table>
<!-- 表の直後に空段落を置く（Wordが表の後に必ず入れる） -->
<p class="MsoNormal"><xsl:text>&#160;</xsl:text></p>
</xsl:template>

<xsl:template match="row">
<tr>
<xsl:apply-templates select="cell"/>
</tr>
</xsl:template>

<xsl:template match="cell">
  <!-- 同じ行のセル数から列幅を求める -->
  <xsl:variable name="cols" select="count(../cell)"/>
  <xsl:variable name="ptw" select="424.65 div $cols"/>
  <xsl:variable name="pxw" select="round(566 div $cols)"/>

  <td valign="top">
    <xsl:attribute name="width"><xsl:value-of select="$pxw"/></xsl:attribute>
    <xsl:attribute name="style">
      <xsl:text>width:</xsl:text>
      <xsl:value-of select="format-number($ptw, '0.00')"/>
      <xsl:text>pt;border:solid windowtext 1.0pt;</xsl:text>
      <!-- 2列目以降は左罫線を消す（隣のセルの右罫線と重なるため） -->
      <xsl:if test="position() &gt; 1">
        <xsl:text>border-left:none;</xsl:text>
      </xsl:if>
      <xsl:text>padding:0cm 5.4pt 0cm 5.4pt</xsl:text>
    </xsl:attribute>

    <p class="MsoNormal" style="margin-bottom:0cm;line-height:normal">
      <xsl:apply-templates/>
    </p>
  </td>
</xsl:template>

</xsl:stylesheet>