"""
通知PDF → XML 変換ツール

Claude APIを使って通知PDFを読み取り、指定スキーマのXMLに変換する。

使い方:
    python pdf2xml.py input.pdf
    python pdf2xml.py input.pdf -o output.xml
    python pdf2xml.py input.pdf --encoding shift_jis
    python pdf2xml.py *.pdf                           # 一括変換
"""

import argparse
import base64
import glob
import os
import re
import sys

from dotenv import load_dotenv
load_dotenv()

import anthropic
from lxml import etree

# ========================================
# 設定
# ========================================
MODEL = "claude-opus-4-8"
MAX_TOKENS = 64000

SCHEMA_DESCRIPTION = """
出力XMLは以下のスキーマに厳密に従ってください。XML以外のテキストは一切出力しないでください。

## 最重要ルール: 全文を転記すること

これは**要約タスクではなく、転記タスク**です。

- 原文の文章を**一字一句そのまま**XMLに書き出すこと
- 要約、短縮、言い換え、意訳を**一切行わない**
- 「以下同様」「(略)」「等」などで省略しない
- 長い段落でも、途中で切らずに最後まで書き切ること
- 文書が長い場合でも、全ての項目を漏れなく出力すること
- 下記スキーマ例の「内容テキスト」等は書式を示すための省略表記であり、
  実際の出力では原文の全文をそのまま入れること
-しかし、***以下の文字ルールは絶対的に優先すること***

## 文字ルール

- 数字・アルファベット・括弧は半角 
- 空白スペースは全角
- 環境依存文字の置換: ⑴→(1)、㉑→((21))
- ページ番号、個人名、「(公印省略)」は削除
-(1).地方自治体の…　のように接頭辞のあとに.がある場合必ず除去すること　

## XML特殊文字のルール（必ず守ること）

原文中の次の3文字は、XMLでは特別な意味を持つため、そのまま書くと文書が壊れます。
必ず置き換えてください。

- `&` → `&amp;`
- `<` → `&lt;`
- `>` → `&gt;`

例: 原文が「A&B株式会社」の場合
- 正: <content>A&amp;B株式会社</content>
- 誤: <content>A&B株式会社</content>

これはタグとして使う<content>等の記号には適用しません。
**本文テキストの中に現れる場合のみ**置き換えてください。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<notification>
  <notificationtitle>件名テキスト</notificationtitle>
  <date>令和○年○月○日</date>
  <department>
   文書種別番号（例:総行行144号/0803児発22号）
  </department>
  <recipient>宛先（例: 各都道府県知事）</recipient>
  <source>発信者（例: 総務省自治行政局長）</source>
  <body>
    <paragraph>本文段落テキスト</paragraph>
    <marker>記</marker>
    <section level="0">
      <subtitle>第一　基本事項</subtitle>
      <content>内容テキスト</content>
　　<content>内容テキスト</content>
    </section>
    <section level="1">
      <subtitle>ア　対象範囲</subtitle>
      <content>内容テキスト</content>
      <content>内容テキスト</content>
    </section>
  </body>
</notification>
```

## 各要素の説明

- notificationtitle: 通知の件名。末尾の「(通知)」は削除する
- date: 発出日
- department: 文書種別番号（例: 総行行第11号、児発0803第1号 等）複数の場合は/区切り

- recipient: 宛先。敬称（殿等）は削除する。複数の場合は**必ず「、」区切り**　
- source: 発信者（役職名のみ。個人名は削除）
- body/paragraph: 本文段落（記書きの前の部分）。段落ごとに1つのparagraphタグ
- body/marker: 「記」がある場合のみ。テキストは「記」固定
- body/section: 記書き項目。level属性で階層を表現（0が最上位）。フラットに並べる
- section/subtitle: 項目の見出し（番号含む）。接頭辞の直後には**必ず全角スペース（U+3000）を1つ挿入する**。接頭辞の種類を問わず例外なし。
  - 変換例: `(2) 4年以上...` → `(2)　4年以上...`（半角スペースを全角スペースに置換）
  - 変換例: `第一 基本事項` → `第一　基本事項`
  - 変換例: `ア 対象範囲` → `ア　対象範囲`
  - 接頭辞後のスペースが半角・全角・なしを問わず、出力は必ず全角スペース1つにすること
  - 
- section/content: 項目の内容テキスト 
  - 1つの項目に複数の段落がある場合、**段落ごとに<content>タグを分ける**
  - 原文で改行され、次の行が字下げされている箇所が段落の区切り
  - 1つの<content>に複数段落を詰め込まないこと

   例: 原文が
    　 外部監査人の住所の告示については、…影響を与えるものではないこと。
    　 その上で、改正前の住所告示については、…適切に対応いただきたいこと。
        の場合（2段落）

  正しい出力:
    <content>外部監査人の住所の告示については、…影響を与えるものではないこと。</content>
    <content>その上で、改正前の住所告示については、…適切に対応いただきたいこと。</content>

  誤った出力（1つのcontentに2段落を入れてはならない）:
    <content>外部監査人の…ものではないこと。その上で、…いただきたいこと。</content>

## underline タグのルール

- 原文で**下線が引かれている箇所**は<underline>タグで囲む
- 下線は文中の一部にだけ引かれることが多いので、その範囲だけを正確に囲む
- 例: <content>この規定は<underline>令和8年4月1日</underline>から適用する。</content>
- 下線がない文書では、このタグは一切使わない
- 傍点・太字・斜体は対象外。**下線のみ**を対象とする

## sectionのlevelルール

- level属性はインデント構造と文書構造から判断する
- 接頭辞の種類（第一/一/1/(1)/ア等）でlevelを決めつけない
- 同じ接頭辞でも文脈によりlevelが異なる場合がある


"""

SYSTEM_PROMPT = f"""あなたは日本の省庁が発出した通知文書PDFを構造化XMLに変換するエキスパートです。
与えられたPDFを読み取り、以下のスキーマに従ってXMLを出力してください。

{SCHEMA_DESCRIPTION}
"""

USER_PROMPT = """このPDFは日本の省庁が発出した通知文書です。
スキーマに従ってXMLを出力してください。

**原文の全文を一字一句そのまま転記してください。要約・短縮・省略は一切しないでください。**
文書が長い場合でも、最後の項目まで漏れなく出力してください。

下線が引かれている箇所は<underline>タグで囲んでください（下線がなければ使わない）。
XMLのみを出力し、それ以外のテキストは一切含めないでください。
必ず <?xml version="1.0" encoding="UTF-8"?> で開始してください。"""


def repair_ampersands(xml_text):
    """
    エスケープされていない & を &amp; に直す。

    AIが原文中の「A&B」をそのまま書いてしまうと、XMLとして壊れる。
    既に正しく書かれている &amp; &lt; &gt; &#123; 等はそのまま残す。
    """
    # 「& のうち、正しい実体参照の始まりではないもの」だけを置換する
    return re.sub(r'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', xml_text)


# 閉じタグの修復対象にするタグ
# これ以外は触らない（誤修正を避けるため）
REPAIRABLE_TAGS = ("subtitle", "content", "paragraph", "notificationtitle",
                   "date", "department", "recipient", "source", "marker")


def repair_mismatched_tags(xml_text):
    """
    開始タグと閉じタグの名前が食い違っている箇所を直す。

    AIが長文を書いている途中で開始時の文脈を見失い、
    <subtitle>…（千文字）…</content> のように
    別のタグ名で閉じてしまうことがある。
    開始タグを正として、閉じタグ側を書き換える。

    戻り値: (直したXML, 修正した箇所数)
    """
    token = re.compile(r'<(/?)(' + '|'.join(REPAIRABLE_TAGS) + r')(\s[^>]*)?>')

    stack = []   # 開いているタグ
    fixes = []   # (位置, 元の文字列, 直した文字列)

    for m in token.finditer(xml_text):
        is_close = m.group(1) == "/"
        name = m.group(2)

        if not is_close:
            stack.append(name)
            continue

        if not stack:
            continue  # 対応する開始タグがない。触らない

        expected = stack[-1]
        if name == expected:
            stack.pop()
            continue

        # 名前が食い違っている → 直前に開いたタグ名で閉じ直す
        fixes.append((m.start(), m.group(0), f"</{expected}>"))
        stack.pop()

    if not fixes:
        return xml_text, 0

    # 後ろから置換する（前からだと位置がずれるため）
    result = xml_text
    for pos, old, new in reversed(fixes):
        result = result[:pos] + new + result[pos + len(old):]

    return result, len(fixes)


def repair_xml(xml_text):
    """
    壊れたXMLを直せる範囲で直す。

    1. 閉じタグの名前の食い違い
    2. エスケープ漏れの &

    戻り値: (直したXML, 何を直したかの説明リスト)
    直らなかった場合は元のXMLをそのまま返す。
    """
    notes = []
    text = xml_text

    # すでに正しければ何もしない
    try:
        etree.fromstring(text.encode("utf-8"))
        return text, notes
    except etree.XMLSyntaxError:
        pass

    # 1. 閉じタグの食い違いを直す
    fixed, n = repair_mismatched_tags(text)
    if n:
        try:
            etree.fromstring(fixed.encode("utf-8"))
            return fixed, [f"閉じタグの不一致を{n}箇所修正しました"]
        except etree.XMLSyntaxError:
            text = fixed
            notes.append(f"閉じタグの不一致を{n}箇所修正しました")

    # 2. & のエスケープ漏れを直す
    fixed = repair_ampersands(text)
    if fixed != text:
        try:
            etree.fromstring(fixed.encode("utf-8"))
            return fixed, notes + ["&のエスケープ漏れを修正しました"]
        except etree.XMLSyntaxError:
            pass

    # 直らなかった。元のまま返す
    return xml_text, []


def pdf_to_xml(pdf_path, api_key):
    """PDFをClaude APIに送信してXMLを取得する"""
    client = anthropic.Anthropic(api_key=api_key)

    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    # 長い文書に対応するためストリーミングで受信する
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": USER_PROMPT},
                ],
            }
        ],
    ) as stream:
        message = stream.get_final_message()

    response_text = ""
    for block in message.content:
        if block.type == "text":
            response_text += block.text

    # ```xml ... ``` の囲みを除去
    xml_text = re.sub(r'^```xml\s*', '', response_text.strip())
    xml_text = re.sub(r'\s*```$', '', xml_text)

    # XMLとして壊れていたら、直せる範囲で修復する
    xml_text, repair_notes = repair_xml(xml_text)

    return xml_text, message.usage, message.stop_reason, repair_notes


def validate_xml(xml_text):
    """XMLが整形式かチェックする。エラーがあれば例外を投げる。"""
    etree.fromstring(xml_text.encode("utf-8"))


def save_xml(xml_text, output_path, encoding="utf-8"):
    """XMLを指定エンコーディングで保存する"""
    # パースして整形
    tree = etree.fromstring(xml_text.encode("utf-8"))
    pretty = etree.tostring(tree, encoding="unicode", pretty_print=True)

    # encoding宣言を付加
    declaration = f'<?xml version="1.0" encoding="{encoding}"?>\n'
    xml_content = declaration + pretty

    with open(output_path, "w", encoding=encoding) as f:
        f.write(xml_content)


def main():
    parser = argparse.ArgumentParser(description="通知PDF → XML 変換（Claude API使用）")
    parser.add_argument("pdf", help="変換対象のPDFファイル（ワイルドカード可）")
    parser.add_argument("-o", "--output", help="出力先XMLファイル（省略時はPDFと同名.xml）")
    parser.add_argument("--encoding", default="utf-8",
                        help="出力エンコーディング（デフォルト: utf-8）")
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_API_KEY", ""),
                        help="Anthropic APIキー（環境変数ANTHROPIC_API_KEYでも可）")
    args = parser.parse_args()

    if not args.api_key:
        print("❌ APIキーが設定されていません")
        print("   環境変数: $env:ANTHROPIC_API_KEY = 'sk-ant-...'")
        print("   または: python pdf2xml.py input.pdf --api-key sk-ant-...")
        sys.exit(1)

    # ワイルドカード展開
    pdf_files = glob.glob(args.pdf)
    if not pdf_files:
        print(f"❌ PDFファイルが見つかりません: {args.pdf}")
        sys.exit(1)

    if len(pdf_files) > 1 and args.output:
        print("❌ 複数PDF指定時は -o オプションは使えません")
        sys.exit(1)

    print(f"📄 通知PDF → XML 変換")
    print(f"   対象: {len(pdf_files)}件")
    print(f"   エンコーディング: {args.encoding}")
    print()

    success = 0
    for pdf_path in pdf_files:
        print(f"  🔄 {pdf_path} を変換中...")
        try:
            xml_text, usage, stop_reason, repair_notes = pdf_to_xml(pdf_path, args.api_key)
            print(f"     API: 入力{usage.input_tokens:,} / 出力{usage.output_tokens:,} tokens")

            for note in repair_notes:
                print(f"     🔧 {note}")

            # 出力が上限で打ち切られていないかチェック
            if stop_reason == "max_tokens":
                print(f"     ⚠️ 出力がトークン上限({MAX_TOKENS:,})に達して途中で切れました")
                print(f"        文書が長すぎます。PDFを分割して変換してください")

            # XML検証
            validate_xml(xml_text)
            print(f"     ✅ XML整形式チェック OK")

            # 保存
            if args.output:
                out_path = args.output
            else:
                out_path = os.path.splitext(pdf_path)[0] + ".xml"

            save_xml(xml_text, out_path, args.encoding)
            print(f"     → {out_path}")
            success += 1

        except etree.XMLSyntaxError as e:
            print(f"     ❌ XML構文エラー: {e}")
            # エラーでも生テキストを保存
            err_path = os.path.splitext(pdf_path)[0] + "_error.xml"
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(xml_text)
            print(f"     → 生テキストを {err_path} に保存しました（手動修正用）")
        except Exception as e:
            print(f"     ❌ エラー: {e}")

    print(f"\n完了: {success}/{len(pdf_files)}件 変換成功")


if __name__ == "__main__":
    main()
