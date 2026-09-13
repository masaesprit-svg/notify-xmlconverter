"""
PDF → RTF 変換ツール（各ページを画像として貼り付け）

PDFの各ページを画像に変換し、1ページに1枚ずつ貼り付けた
RTFファイルを作る。

これまでスクリーンショットを撮ってWordに貼っていた作業を
自動化するもの。画面の表示倍率に左右されないため、
スクリーンショットより鮮明になる。

必要なもの:
    pip install pymupdf

使い方:
    python pdf2rtf.py input.pdf
    python pdf2rtf.py input.pdf -o output.rtf
    python pdf2rtf.py *.pdf                  # 一括変換
    python pdf2rtf.py input.pdf --dpi 200    # 画質を上げる
"""

import argparse
import glob
import os
import sys

try:
    import pymupdf
except ImportError:
    print("❌ PyMuPDFが入っていません。次のコマンドで入れてください:")
    print("    python -m pip install pymupdf")
    sys.exit(1)


# 既定の解像度
# 通知文書は白黒なので、グレースケールにすると容量が約半分になる。
# そのぶん解像度を上げても、カラーの96dpiと同程度の容量に収まる。
DEFAULT_DPI = 150

# 既定でグレースケールにするか
# 図表がカラーの文書では False にする（--color オプション）
DEFAULT_GRAY = True

# 余白（twip単位。1pt = 20twip、1inch = 1440twip）
# 画像をページいっぱいに置くため、余白は最小にする
MARGIN = 0


def build_rtf(pdf_path, dpi=DEFAULT_DPI, gray=DEFAULT_GRAY):
    """
    PDFを読んで、各ページを画像として貼り付けたRTFの中身を組み立てる。

    戻り値: (RTF文字列, ページ数)
    """
    doc = pymupdf.open(pdf_path)
    pages = len(doc)

    if pages == 0:
        doc.close()
        raise ValueError("ページがありません")

    # --- 用紙サイズを1ページ目から決める ---
    first = doc[0].rect
    paper_w = int(first.width * 20)    # pt → twip
    paper_h = int(first.height * 20)

    parts = []

    # RTFヘッダ
    # \rtf1     RTF形式
    # \ansi     文字コード
    # \deff0    既定フォント
    # \paperw   用紙の幅（twip）
    # \marg*    余白（twip）
    parts.append(r"{\rtf1\ansi\ansicpg932\deff0")
    parts.append(r"{\fonttbl{\f0\fnil\fcharset128 MS Mincho;}}")
    parts.append(
        f"\\paperw{paper_w}\\paperh{paper_h}"
        f"\\margl{MARGIN}\\margr{MARGIN}"
        f"\\margt{MARGIN}\\margb{MARGIN}"
    )

    for i, page in enumerate(doc):
        # ページを画像にする
        if gray:
            pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        else:
            pix = page.get_pixmap(dpi=dpi)
        png = pix.tobytes("png")

        # RTFには16進数の文字列として埋め込む
        hexdata = png.hex()

        # 画像の配置サイズ（元のページサイズに合わせる）
        w_twip = int(page.rect.width * 20)
        h_twip = int(page.rect.height * 20)

        # \pict        画像の開始
        # \pngblip     PNG形式
        # \picw \pich  画像本来のサイズ
        # \picwgoal    実際に表示するサイズ（twip）
        parts.append(r"{\pard")
        parts.append(
            r"{\pict\pngblip"
            f"\\picw{pix.width}\\pich{pix.height}"
            f"\\picwgoal{w_twip}\\pichgoal{h_twip} "
        )
        parts.append(hexdata)
        parts.append(r"}")
        parts.append(r"\par}")

        # 最後のページ以外は改ページを入れる
        # （1ページに1枚ずつ配置するため）
        if i < pages - 1:
            parts.append(r"\page")

    parts.append(r"}")
    doc.close()

    return "".join(parts), pages


def convert(pdf_path, output_path=None, dpi=DEFAULT_DPI, gray=DEFAULT_GRAY):
    """PDFをRTFに変換して保存する"""
    rtf, pages = build_rtf(pdf_path, dpi, gray)

    if not output_path:
        output_path = os.path.splitext(pdf_path)[0] + ".rtf"

    # RTFは16進数と制御文字だけなのでASCIIで書き出す
    with open(output_path, "w", encoding="ascii") as f:
        f.write(rtf)

    return output_path, pages


def main():
    parser = argparse.ArgumentParser(
        description="PDF → RTF 変換（各ページを画像として貼り付け）"
    )
    parser.add_argument("pdf", help="変換対象のPDFファイル（ワイルドカード可）")
    parser.add_argument("-o", "--output",
                        help="出力先RTFファイル（省略時はPDFと同名.rtf）")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI,
                        help=f"画像の解像度（既定: {DEFAULT_DPI}）")
    parser.add_argument("--color", action="store_true",
                        help="カラーで出力する（既定はグレースケール。容量が約2倍になる）")
    args = parser.parse_args()

    gray = not args.color

    pdf_files = glob.glob(args.pdf)
    if not pdf_files:
        print(f"❌ PDFファイルが見つかりません: {args.pdf}")
        sys.exit(1)

    if len(pdf_files) > 1 and args.output:
        print("❌ 複数PDF指定時は -o オプションは使えません")
        sys.exit(1)

    print("📄 PDF → RTF 変換（各ページを画像として貼り付け）")
    print(f"   解像度: {args.dpi} dpi / {'グレースケール' if gray else 'カラー'}")
    print(f"   対象: {len(pdf_files)}件")
    print()

    success = 0
    for pdf_path in pdf_files:
        name = os.path.basename(pdf_path)
        print(f"  🔄 {name} を変換中...")

        try:
            out_path, pages = convert(pdf_path, args.output, args.dpi, gray)
            size_mb = os.path.getsize(out_path) / 1024 / 1024
            print(f"     {pages}ページ / {size_mb:.1f}MB")
            print(f"     ✅ → {os.path.basename(out_path)}")
            success += 1

        except Exception as e:
            print(f"     ❌ エラー: {e}")

    print()
    print(f"完了: {success}/{len(pdf_files)}件 変換成功")


if __name__ == "__main__":
    main()
