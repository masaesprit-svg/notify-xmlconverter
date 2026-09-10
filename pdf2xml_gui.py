"""
通知PDF → XML 変換ツール（GUI版）

PDFファイルをウィンドウにドラッグ&ドロップすると、
確認ダイアログのあと、同じフォルダにXMLファイルを出力します。

必要なもの:
    pip install anthropic lxml python-dotenv tkinterdnd2

使い方:
    python pdf2xml_gui.py
"""

import os
import queue
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from lxml import etree

# ----------------------------------------
# 変換ロジックは pdf2xml.py から借りてくる
# （同じフォルダに pdf2xml.py を置いてください）
# ----------------------------------------
from pdf2xml import pdf_to_xml, validate_xml, save_xml

# ----------------------------------------
# ドラッグ&ドロップ用ライブラリ
# 入っていなくても「ファイルを選ぶ」ボタンで動くようにする
# ----------------------------------------
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False


APP_TITLE = "通知PDF → XML/HTM 変換ツール"
ENCODING = "utf-8"          # XMLの文字コード
HTM_ENCODING = "shift_jis"  # HTMの文字コード（社内システム取込用）
XSL_FILENAME = "notification.xsl"

# 同時に処理する件数
# 増やすほど速くなるが、多すぎるとAPIの制限に当たる。5〜6が目安。
MAX_WORKERS = 5


# ========================================
# 実行ファイルの置き場所
# ========================================
def get_base_dir():
    """exe化されていてもスクリプトでも、自分の置き場所を返す"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ========================================
# XML → HTM 変換
# ========================================
def xml_to_htm(xml_path, xsl_path, output_path=None, encoding=HTM_ENCODING):
    """XMLをXSLTで変換してHTMを生成する"""
    transformer = etree.XSLT(etree.parse(xsl_path))
    result = transformer(etree.parse(xml_path))

    if not output_path:
        output_path = os.path.splitext(xml_path)[0] + ".htm"

    html_bytes = etree.tostring(
        result, method="html", encoding=encoding, pretty_print=True
    )
    with open(output_path, "wb") as f:
        f.write(html_bytes)

    return output_path


# ========================================
# APIキーの取得
# ========================================
def get_api_key():
    """環境変数または .env / apikey.env からAPIキーを読む"""
    from dotenv import load_dotenv

    base_dir = get_base_dir()

    for filename in (".env", "apikey.env"):
        path = os.path.join(base_dir, filename)
        if os.path.exists(path):
            load_dotenv(path)
            break

    return os.environ.get("ANTHROPIC_API_KEY", "")


# ========================================
# メインウィンドウ
# ========================================
class App:
    def __init__(self, root):
        self.root = root
        self.api_key = get_api_key()
        self.xsl_path = os.path.join(get_base_dir(), XSL_FILENAME)
        self.log_queue = queue.Queue()
        self.busy = False

        root.title(APP_TITLE)
        root.geometry("560x420")
        root.minsize(480, 360)

        # --- ドロップエリア ---
        self.drop_area = tk.Label(
            root,
            text=self._drop_text(),
            bg="#e9e9e9",
            fg="#333333",
            relief="ridge",
            bd=2,
            font=("Meiryo UI", 11),
            justify="center",
        )
        self.drop_area.pack(fill="both", expand=False, padx=16, pady=(16, 8), ipady=40)

        if DND_AVAILABLE:
            self.drop_area.drop_target_register(DND_FILES)
            self.drop_area.dnd_bind("<<Drop>>", self.on_drop)

        # --- ボタン ---
        btn_frame = tk.Frame(root)
        btn_frame.pack(fill="x", padx=16)

        self.select_btn = tk.Button(
            btn_frame,
            text="ファイルを選ぶ...",
            command=self.on_select_files,
            font=("Meiryo UI", 10),
            width=16,
        )
        self.select_btn.pack(side="left")

        # --- 進捗バー ---
        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill="x", padx=16, pady=(12, 4))

        # --- ログ表示 ---
        log_frame = tk.Frame(root)
        log_frame.pack(fill="both", expand=True, padx=16, pady=(4, 16))

        self.log = tk.Text(
            log_frame,
            height=8,
            font=("Consolas", 9),
            bg="#fafafa",
            state="disabled",
            wrap="word",
        )
        scrollbar = tk.Scrollbar(log_frame, command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # APIキーが無ければ警告
        if not self.api_key:
            self.write_log("[警告] APIキーが見つかりません。")
            self.write_log("　このアプリと同じフォルダに .env を置いて、")
            self.write_log("　ANTHROPIC_API_KEY=sk-ant-... と書いてください。")
        elif not os.path.exists(self.xsl_path):
            self.write_log(f"[警告] {XSL_FILENAME} が見つかりません。")
            self.write_log("　このアプリと同じフォルダに置いてください。")
            self.write_log("　（XMLは作れますが、HTMは作れません）")
        else:
            self.write_log("準備完了です。PDFをドラッグ&ドロップしてください。")
            self.write_log("XMLとHTMの両方を出力します。")

        # ログの定期チェック（別スレッドからの書き込み用）
        self.root.after(100, self.poll_log)

    def _drop_text(self):
        if DND_AVAILABLE:
            return "ここに PDF をドラッグ&ドロップ\n\n（複数まとめてでもOK）"
        return "下の「ファイルを選ぶ...」から\nPDFを選んでください\n\n※ドラッグ&ドロップを使うには\n   pip install tkinterdnd2"

    # ------------------------------------
    # ログ出力
    # ------------------------------------
    def write_log(self, text):
        """メインスレッドから直接ログを書く"""
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll_log(self):
        """別スレッドから送られたログを画面に反映する"""
        while not self.log_queue.empty():
            kind, payload = self.log_queue.get()
            if kind == "log":
                self.write_log(payload)
            elif kind == "progress":
                self.progress["value"] = payload
            elif kind == "done":
                self.finish(payload)
        self.root.after(100, self.poll_log)

    # ------------------------------------
    # ファイル受け取り
    # ------------------------------------
    def on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        self.handle_files(paths)

    def on_select_files(self):
        paths = filedialog.askopenfilenames(
            title="変換するPDFを選んでください",
            filetypes=[("PDFファイル", "*.pdf"), ("すべてのファイル", "*.*")],
        )
        self.handle_files(paths)

    def handle_files(self, paths):
        if self.busy:
            messagebox.showinfo(APP_TITLE, "変換中です。終わるまでお待ちください。")
            return

        if not self.api_key:
            messagebox.showerror(
                APP_TITLE,
                "APIキーが設定されていません。\n\n"
                "このアプリと同じフォルダに .env というファイルを作り、\n"
                "ANTHROPIC_API_KEY=sk-ant-...\n"
                "と書いて保存してください。",
            )
            return

        # PDFだけに絞る
        pdfs = [p for p in paths if p.lower().endswith(".pdf")]
        skipped = len(paths) - len(pdfs)

        if not pdfs:
            messagebox.showwarning(APP_TITLE, "PDFファイルが見つかりませんでした。")
            return

        # 確認ダイアログ
        names = "\n".join("・" + os.path.basename(p) for p in pdfs[:10])
        if len(pdfs) > 10:
            names += f"\n　...ほか{len(pdfs) - 10}件"

        msg = f"次の{len(pdfs)}件を変換しますか？\n\n{names}"
        if skipped:
            msg += f"\n\n（PDF以外の{skipped}件は無視されます）"
        msg += "\n\n※XMLとHTMがPDFと同じフォルダに出力されます"

        if not messagebox.askyesno(APP_TITLE, msg):
            self.write_log("キャンセルしました。")
            return

        self.start_conversion(pdfs)

    # ------------------------------------
    # 変換処理（別スレッドで実行）
    # ------------------------------------
    def start_conversion(self, pdfs):
        self.busy = True
        self.select_btn.configure(state="disabled")
        self.progress["value"] = 0
        self.progress["maximum"] = len(pdfs)

        workers = min(MAX_WORKERS, len(pdfs))

        self.write_log("")
        self.write_log(f"=== 変換開始（{len(pdfs)}件）===")
        if workers > 1:
            self.write_log(f"    {workers}件ずつ同時に処理します")

        thread = threading.Thread(target=self.worker, args=(pdfs,), daemon=True)
        thread.start()

    def convert_one(self, pdf_path, index, total):
        """
        PDF1件を変換する。複数スレッドから同時に呼ばれる。

        画面には直接触らず、ログはキュー経由で送る。
        戻り値: 成功したら True
        """
        name = os.path.basename(pdf_path)
        lines = []          # この1件のログをまとめてから送る
        xml_text = None
        ok = False

        try:
            xml_text, usage, stop_reason, repair_notes = pdf_to_xml(pdf_path, self.api_key)
            lines.append(
                f"      API: 入力{usage.input_tokens:,} / 出力{usage.output_tokens:,} tokens"
            )

            for note in repair_notes:
                lines.append(f"      🔧 {note}")

            if stop_reason == "max_tokens":
                lines.append("      ⚠️ 出力が上限に達して途中で切れました。PDFを分割してください")

            validate_xml(xml_text)

            out_path = os.path.splitext(pdf_path)[0] + ".xml"
            save_xml(xml_text, out_path, ENCODING)
            lines.append(f"      XML → {os.path.basename(out_path)}")

            # 続けてHTMに変換する
            if os.path.exists(self.xsl_path):
                try:
                    htm_path = xml_to_htm(out_path, self.xsl_path)
                    lines.append(f"      HTM → {os.path.basename(htm_path)}")
                except Exception as e:
                    lines.append(f"      ⚠️ HTM変換に失敗しました: {e}")
                    lines.append("         XMLは出力済みです")
            else:
                lines.append(f"      ⚠️ {XSL_FILENAME} がないためHTMは作成しません")

            ok = True

        except Exception as e:
            lines.append(f"      失敗: {e}")

            # 原因を調べられるよう、AIの生の応答を残しておく
            if xml_text:
                err_path = os.path.splitext(pdf_path)[0] + "_error.xml"
                try:
                    with open(err_path, "w", encoding="utf-8") as f:
                        f.write(xml_text)
                    lines.append(
                        f"      → 生データを {os.path.basename(err_path)} に保存しました"
                    )
                except Exception:
                    pass

        # 1件分をまとめて送る。
        # 同時処理では終わる順序が前後するため、1行ずつ送ると
        # 別のファイルのログと混ざって読みにくくなる。
        header = f"[{index}/{total}] {name}"
        self.log_queue.put(("log", "\n".join([header] + lines)))

        return ok

    def worker(self, pdfs):
        """バックグラウンドで変換する（画面が固まらないように）"""
        total = len(pdfs)
        workers = min(MAX_WORKERS, total)
        done = 0
        success = 0

        # 完了した件数を数えるための鍵
        # 複数スレッドが同時に数を増やすと壊れるため
        lock = threading.Lock()

        def run(args):
            nonlocal done, success
            index, pdf_path = args
            ok = self.convert_one(pdf_path, index, total)

            with lock:
                done += 1
                if ok:
                    success += 1
                self.log_queue.put(("progress", done))

        jobs = list(enumerate(pdfs, start=1))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(run, jobs))

        self.log_queue.put(("done", (success, total)))

    def finish(self, result):
        success, total = result
        self.busy = False
        self.select_btn.configure(state="normal")

        self.write_log(f"=== 完了: {success}/{total}件 成功 ===")

        if success == total:
            messagebox.showinfo(APP_TITLE, f"{success}件すべて変換しました。")
        else:
            messagebox.showwarning(
                APP_TITLE,
                f"{success}/{total}件が成功しました。\n"
                f"失敗した分はログを確認してください。",
            )


# ========================================
# 起動
# ========================================
def main():
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
