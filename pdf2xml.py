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
MODEL = "claude-sonnet-4-5-20250929"
MAX_TOKENS = 8192

SCHEMA_DESCRIPTION = """
出力XMLは以下のスキーマに厳密に従ってください。XML以外のテキストは一切出力しないでください。

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
    </section>
    <section level="1">
      <subtitle>ア　対象範囲</subtitle>
      <content>内容テキスト</content>
    </section>
  </body>
</notification>
```

## 各要素の説明

- notificationtitle: 通知の件名。末尾の「(通知)」は削除する
- date: 発出日
- department: 文書種別番号（例: 総行行第11号、児発0803第1号 等）複数の場合は/区切り

- recipient: 宛先。敬称（殿等）は削除する。複数の場合はカンマ区切り
- source: 発信者（役職名のみ。個人名は削除）
- body/paragraph: 本文段落（記書きの前の部分）。段落ごとに1つのparagraphタグ
- body/marker: 「記」がある場合のみ。テキストは「記」固定
- body/section: 記書き項目。level属性で階層を表現（0が最上位）。フラットに並べる
- section/subtitle: 項目の見出し（番号含む）
- section/content: 項目の内容テキスト

## sectionのlevelルール

- level属性はインデント構造と文書構造から判断する
- 接頭辞の種類（第一/一/1/(1)/ア等）でlevelを決めつけない
- 同じ接頭辞でも文脈によりlevelが異なる場合がある

## 文字ルール

- 数字・アルファベット・括弧は半角
- 空白スペースは全角
- 環境依存文字の置換: ⑴→(1)、㉑→((21))
- ページ番号、個人名、「(公印省略)」は削除
"""

SYSTEM_PROMPT = f"""あなたは日本の省庁が発出した通知文書PDFを構造化XMLに変換するエキスパートです。
与えられたPDFを読み取り、以下のスキーマに従ってXMLを出力してください。

{SCHEMA_DESCRIPTION}
"""

USER_PROMPT = """このPDFは日本の省庁が発出した通知文書です。
スキーマに従ってXMLを出力してください。
XMLのみを出力し、それ以外のテキストは一切含めないでください。
必ず <?xml version="1.0" encoding="UTF-8"?> で開始してください。"""


def pdf_to_xml(pdf_path, api_key):
    """PDFをClaude APIに送信してXMLを取得する"""
    client = anthropic.Anthropic(api_key=api_key)

    with open(pdf_path, "rb") as f:
        pdf_b64 = base64.standard_b64encode(f.read()).decode("utf-8")

    message = client.messages.create(
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
    )

    response_text = ""
    for block in message.content:
        if block.type == "text":
            response_text += block.text

    # ```xml ... ``` の囲みを除去
    xml_text = re.sub(r'^```xml\s*', '', response_text.strip())
    xml_text = re.sub(r'\s*```$', '', xml_text)

    return xml_text, message.usage


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
            xml_text, usage = pdf_to_xml(pdf_path, args.api_key)
            print(f"     API: 入力{usage.input_tokens:,} / 出力{usage.output_tokens:,} tokens")

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
