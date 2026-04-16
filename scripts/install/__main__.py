# -*- coding: utf-8 -*-
"""
aitex 启动器入口 (Bootstrap)
━━━━━━━━━━━━━━━━━━━━━━━━━━
PyInstaller 真正的入口文件。
通过 exec 方式加载 hub.py，绕过 PyInstaller 静态 import 分析。
"""

import sys
import os


def main():
    # 确定 install 模块所在目录
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
        install_dir = os.path.join(base_dir, "scripts", "install")
    else:
        install_dir = os.path.dirname(os.path.abspath(__file__))

    # 确保 install 目录在最前面
    if install_dir not in sys.path:
        sys.path.insert(0, install_dir)

    # 项目根目录
    if not getattr(sys, 'frozen', False):
        proj_dir = os.path.dirname(os.path.dirname(install_dir))
        if proj_dir not in sys.path:
            sys.path.insert(0, proj_dir)

    # 用 exec 加载 hub.py（绕过 PyInstaller 的静态 import 分析）
    hub_path = os.path.join(install_dir, "hub.py")

    with open(hub_path, "r", encoding="utf-8") as f:
        hub_code = f.read()

    # 构建执行命名空间
    run_globals = {
        "__name__": "__main__",
        "__file__": hub_path,
        "__builtins__": __builtins__,
    }
    # 注入必要的模块
    run_globals["sys"] = sys
    run_globals["os"] = os

    # 写入调试日志
    try:
        log_dir = os.environ.get("AITEX_LOG_DIR", "")
        if not log_dir:
            # 尝试常见位置
            for candidate in [
                os.path.join(install_dir, "..", "..", "..", "logs"),
                os.path.join(os.path.dirname(sys.executable), "..", "..", "logs"),
                "C:\\temp",
            ]:
                c = os.path.abspath(candidate)
                if os.path.isdir(c):
                    log_dir = c
                    break
            else:
                os.makedirs("C:\\temp", exist_ok=True)
                log_dir = "C:\\temp"

        log_file = os.path.join(log_dir, "bootstrap_debug.log")
        with open(log_file, "w", encoding="utf-8") as dbg:
            dbg.write(f"install_dir: {install_dir}\n")
            dbg.write(f"hub_path: {hub_path}\n")
            dbg.write(f"hub exists: {os.path.exists(hub_path)}\n")
            dbg.write(f"sys.path[0]: {sys.path[0]}\n")
            dbg.write(f"frozen: {getattr(sys, 'frozen', False)}\n")
            dbg.write(f"exec starting...\n")
    except Exception:
        pass  # 调试日志写入失败不影响主流程

    # 执行 hub.py
    try:
        exec(hub_code, run_globals)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # 写入调试日志
        try:
            with open(log_file, "a", encoding="utf-8") as dbg:
                dbg.write(f"\n!!! EXEC CRASH !!!\n")
                dbg.write(f"Error: {e}\n")
                dbg.write(f"{tb}\n")
        except Exception:
            pass
        # 也尝试写到一个绝对确定能写的位置
        try:
            with open(r"C:\temp\aitex_exec_crash.log", "w", encoding="utf-8") as f:
                f.write(f"Error: {e}\n\n{tb}\n")
        except Exception:
            pass

        # ═══ windowed 模式下弹窗显示错误（否则用户看不到任何东西） ═══
        if getattr(sys, 'frozen', False):
            try:
                import tkinter as tk
                from tkinter import scrolledtext
                root = tk.Tk()
                root.title("aitext - 启动失败")
                root.attributes("-topmost", True)
                # 居中
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                w, h = 560, 400
                x = (sw - w) // 2
                y = (sh - h) // 2
                root.geometry(f"{w}x{h}+{x}+{y}")
                root.resizable(False, False)

                tk.Label(root, text="aitex 启动失败",
                         font=("Arial", 16, "bold"), fg="#dc2626",
                         bg="#1e1e2e").pack(fill="x", pady=(20, 10))
                tk.Label(root, text=str(e)[:200],
                         font=("Arial", 10), fg="#fbbf24",
                         bg="#1e1e2e", wraplength=520).pack(fill="x", padx=20)

                txt = scrolledtext.ScrolledText(
                    root, font=("Consolas", 9), bg="#2d2d3d", fg="#cdd6f4",
                    wrap="word", height=12)
                txt.pack(fill="both", expand=True, padx=15, pady=10)
                txt.insert("end", tb[-2500:] if len(tb) > 2500 else tb)
                txt.config(state="disabled")

                def _copy_and_exit():
                    root.clipboard_clear()
                    root.clipboard_append(tb)
                    root.destroy()

                btn_frame = tk.Frame(root, bg="#1e1e2e")
                btn_frame.pack(fill="x", pady=(5, 15))
                tk.Button(btn_frame, text="复制错误信息并关闭",
                          command=_copy_and_exit,
                          bg="#dc2626", fg="white", font=("Arial", 10),
                          padx=30, pady=8).pack()

                root.mainloop()
            except Exception:
                pass  # tkinter 都不可用就彻底没办法了

        raise  # 重新抛出


if __name__ == "__main__":
    main()
