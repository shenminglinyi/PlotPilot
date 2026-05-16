#!/usr/bin/env python3
"""实时查看日志 - 类似 tail -f"""
import sys
import time
from pathlib import Path

def tail_log(log_file: str, lines: int = 50):
    """实时查看日志文件"""
    log_path = Path(log_file)

    if not log_path.exists():
        print(f"❌ 日志文件不存在: {log_file}")
        print(f"💡 请先启动后端，日志文件会自动创建")
        return

    print("=" * 80)
    print(f"📋 实时日志查看: {log_file}")
    print("=" * 80)
    print(f"显示最近 {lines} 行，然后实时跟踪新日志...")
    print("按 Ctrl+C 退出\n")

    # 读取最后 N 行
    with open(log_path, 'r', encoding='utf-8') as f:
        all_lines = f.readlines()
        recent_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
        for line in recent_lines:
            print(line, end='')

    # 实时跟踪新内容
    with open(log_path, 'r', encoding='utf-8') as f:
        f.seek(0, 2)  # 移到文件末尾
        try:
            while True:
                line = f.readline()
                if line:
                    print(line, end='')
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n👋 停止日志查看")

if __name__ == "__main__":
    log_file = sys.argv[1] if len(sys.argv) > 1 else "logs/plotpilot.log"
    lines = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    tail_log(log_file, lines)
