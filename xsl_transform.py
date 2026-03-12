"""
XML → HTML 変換ツール

XSLTファイルを参照してXMLをHTMLに変換する。

使い方:
    python xsl_transform.py input.xml style.xsl
    python xsl_transform.py input.xml style.xsl -o output.html
    python xsl_transform.py input.xml style.xsl -o output.html --encoding shift_jis
    python xsl_transform.py *.xml style.xsl               # 一括変換
"""

import argparse
import glob
import os
import sys
from lxml import etree


def transform(xml_path, xsl_path, output_path=None, encoding="utf-8"):
    """XMLをXSLTで変換してHTMLを生成する"""
    # XSLTを読み込み
    xsl_tree = etree.parse(xsl_path)
    transformer = etree.XSLT(xsl_tree)

    # XMLを読み込み
    xml_tree = etree.parse(xml_path)

    # 変換実行
    result = transformer(xml_tree)

    # エラーがあれば表示
    if transformer.error_log:
        for entry in transformer.error_log:
            if entry.level_name == "ERROR":
                print(f"  ⚠️ XSLT警告: {entry.message}", file=sys.stderr)

    # 出力先の決定
    if not output_path:
        base = os.path.splitext(xml_path)[0]
        output_path = base + ".html"

    # 書き込み
    html_bytes = etree.tostring(result, method="html", encoding=encoding, pretty_print=True)
    with open(output_path, "wb") as f:
        f.write(html_bytes)

    return output_path


def main():
    parser = argparse.ArgumentParser(description="XML → HTML 変換（XSLT使用）")
    parser.add_argument("xml", help="変換対象のXMLファイル（ワイルドカード可）")
    parser.add_argument("xsl", help="XSLTファイルのパス")
    parser.add_argument("-o", "--output", help="出力先HTMLファイル（省略時はXMLと同名.html）")
    parser.add_argument("--encoding", default="utf-8",
                        help="出力エンコーディング（デフォルト: utf-8）")
    args = parser.parse_args()

    # ワイルドカード展開
    xml_files = glob.glob(args.xml)
    if not xml_files:
        print(f"❌ XMLファイルが見つかりません: {args.xml}")
        sys.exit(1)

    # XSLファイル存在チェック
    if not os.path.exists(args.xsl):
        print(f"❌ XSLファイルが見つかりません: {args.xsl}")
        sys.exit(1)

    # 複数ファイルの場合は -o 指定不可
    if len(xml_files) > 1 and args.output:
        print("❌ 複数XMLファイル指定時は -o オプションは使えません")
        sys.exit(1)

    print(f"📄 XSL: {args.xsl}")
    print(f"   エンコーディング: {args.encoding}")
    print(f"   対象: {len(xml_files)}件")
    print()

    success = 0
    for xml_path in xml_files:
        try:
            out = transform(xml_path, args.xsl, args.output, args.encoding)
            print(f"  ✅ {xml_path} → {out}")
            success += 1
        except etree.XSLTApplyError as e:
            print(f"  ❌ {xml_path}: XSLT変換エラー: {e}")
        except etree.XMLSyntaxError as e:
            print(f"  ❌ {xml_path}: XML構文エラー: {e}")
        except Exception as e:
            print(f"  ❌ {xml_path}: {e}")

    print(f"\n完了: {success}/{len(xml_files)}件 変換成功")


if __name__ == "__main__":
    main()
