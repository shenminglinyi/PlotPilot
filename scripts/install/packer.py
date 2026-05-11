# -*- coding: utf-8 -*-
"""
PlotPilot（墨枢）项目打包器
━━━━━━━━━━━━━━━━
将项目打包为 ZIP 分享包（不含敏感文件和大型目录）。
使用 PowerShell 进行过滤复制 + 压缩，保证速度。

小白用户友好:
  - 自动排除 .venv / node_modules / .env 等
  - frontend 只保留 dist/
  - data 只保留空目录结构
  - 打包完成后显示使用说明
"""

import os
import subprocess
import time

from theme import OK_C, ERR_C, ACCENT, TEXT_DIM
from utils import get_proj_dir, NO_WIN


class ProjectPacker:
    """
    项目打包器。

    用法:
      packer = ProjectPacker(on_log, on_progress)
      packer.pack()  # 在后台线程调用
    """

    # 排除的目录
    EXCLUDE_DIRS = [
        '.venv', 'venv', '__pycache__', '.git', 'node_modules',
        'logs', '.models', '.qoder', 'PlotPilot-master',
        '.playwright-mcp', '.pytest_cache', '.claude',
    ]

    # 排除的文件
    EXCLUDE_FILES = [
        'startup_err.log', 'startup_out.log', 'aitext.db',
        'aitext.db-shm', 'aitext.db-wal', '.env', 'aitext.lock',
    ]

    def __init__(self, on_log=None, on_progress=None):
        self.on_log = on_log or (lambda *a: None)
        self.on_progress = on_progress or (lambda *a: None)
        self.proj_dir = get_proj_dir()

    def _log(self, msg, tag="info"):
        self.on_log(msg, tag)

    def _prog(self, pct, label="", icon="⏳"):
        self.on_progress(pct, label, icon)

    def pack(self):
        """执行打包。返回 (success, zip_path)"""
        parent = os.path.dirname(self.proj_dir)
        timestamp = time.strftime('%Y%m%d-%H%M')
        default_zip = os.path.join(parent, f"plotpilot-{timestamp}.zip")

        self._prog(0, "准备打包项目...", "📦")
        self._log("═══ 打包分享模式 ═══", "title")
        self._log(f"输出路径: {default_zip}", "info")

        ps_script = self._build_powershell_script(default_zip)

        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-WindowStyle", "Hidden", "-Command", ps_script],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="gbk", errors="replace", bufsize=1,
                creationflags=NO_WIN,
            )

            step_map = {
                "[1/3]": (10, "正在复制文件..."),
                "[2/3]": (60, "正在压缩..."),
                "[3/3]": (90, "清理临时文件..."),
            }

            for line in proc.stdout:
                line = line.rstrip()
                if not line:
                    continue
                # 进度匹配
                for k, (p, lbl) in step_map.items():
                    if k in line:
                        self._prog(p, lbl, "⚙")
                # 完成信息
                if line.startswith("SIZE_MB="):
                    size_mb = line.split("=", 1)[1]
                    self._prog(100, f"打包完成！{size_mb} MB", "✔")
                    self._log(f"文件大小：{size_mb} MB", "ok")
                    self._log(f"保存位置：{default_zip}", "ok")
                    self._log("═══ 收件人使用步骤 ═══", "title")
                    self._log("  ① 解压 ZIP 文件到任意目录", "info")
                    self._log("  ② 安装 Python 3.10+（勾选 Add to PATH）", "info")
                    self._log("  ③ 双击 tools\\aitext.bat 启动 PlotPilot（墨枢）", "info")
                    return True, default_zip
                else:
                    self._log(line, "info")

            proc.wait()

            # 没有收到 SIZE_MB= 说明中途失败
            self._log("打包流程未正常完成", "error")
            return False, default_zip

        except Exception as e:
            self._log(f"打包异常：{e}", "error")
            self._prog(0, "打包失败", "✘")
            return False, default_zip

    def _build_powershell_script(self, zip_path):
        """生成 PowerShell 过滤复制+压缩脚本"""
        src = self.proj_dir

        # 构建排除列表字符串
        dirs_str = ",".join(f"'{d}'" for d in self.EXCLUDE_DIRS)
        files_str = ",".join(f"'{f}'" for f in self.EXCLUDE_FILES)

        return (
            f"$src = '{src}'.Replace(\"'\",\"''\");\n"
            f"$zipPath = '{zip_path}'.Replace(\"'\",\"''\");\n"
            "$tempDir = Join-Path $env:TEMP ('plotpilot_pack_' + [guid]::NewGuid().ToString('N').Substring(0,8));\n"
            "$folderName = Split-Path $src -Leaf;\n"
            "$destDir = Join-Path $tempDir $folderName;\n"

            "Write-Host '[1/3] 复制文件...';\n"
            f"$excludeDirs = @({dirs_str});\n"
            f"$excludeFiles = @({files_str});\n"

            # 递归过滤复制函数
            "function Copy-Filtered($srcPath, $dstPath) {\n"
            "  if (!(Test-Path $dstPath)) { New-Item -ItemType Directory -Path $dstPath -Force | Out-Null }\n"
            "  foreach ($item in Get-ChildItem -Path $srcPath -Force) {\n"
            "    $relName = $item.Name;\n"
            "    if ($item.PSIsContainer) {\n"
            "      if ($excludeDirs -contains $relName) { continue }\n"
            # frontend 特殊处理：只复制 dist + package.json
            "      if ($relName -eq 'frontend') {\n"
            "        $frontDst = Join-Path $dstPath 'frontend';\n"
            "        New-Item -ItemType Directory -Path $frontDst -Force | Out-Null;\n"
            "        $distSrc = Join-Path $item.FullName 'dist';\n"
            "        if (Test-Path $distSrc) { Copy-Item -Path $distSrc -Destination $frontDst -Recurse -Force }\n"
            "        Copy-Item (Join-Path $item.FullName 'package.json') $frontDst -ErrorAction SilentlyContinue;\n"
            "        continue\n"
            "      }\n"
            # data 特殊处理：只保留空目录结构
            "      if ($relName -eq 'data') {\n"
            "        $dataDst = Join-Path $dstPath 'data';\n"
            "        New-Item -ItemType Directory -Path $dataDst -Force | Out-Null;\n"
            "        New-Item -ItemType Directory -Path (Join-Path $dataDst 'chromadb') -Force | Out-Null;\n"
            "        New-Item -ItemType Directory -Path (Join-Path $dataDst 'logs') -Force | Out-Null;\n"
            "        foreach ($df in Get-ChildItem -Path $item.FullName -File) { if ($excludeFiles -notcontains $df.Name) { Copy-Item $df.FullName (Join-Path $dataDst $df.Name) -Force } }\n"
            "        continue\n"
            "      }\n"
            "      Copy-Filtered $item.FullName (Join-Path $dstPath $relName)\n"
            "    } else {\n"
            "      if ($excludeFiles -contains $relName) { continue }\n"
            "      if ($relName -match '\\.(pyc|pyo|egg)$') { continue }\n"
            "      Copy-Item $item.FullName (Join-Path $dstPath $relName) -Force\n"
            "    }\n"
            "  }\n"
            "}\n"

            "Copy-Filtered $src $destDir;\n"
            "New-Item -ItemType Directory -Path (Join-Path $destDir 'logs') -Force | Out-Null;\n"

            "Write-Host '[2/3] 压缩文件...';\n"
            "if (Test-Path $zipPath) { Remove-Item $zipPath -Force }\n"
            "Add-Type -AssemblyName System.IO.Compression.FileSystem;\n"
            "[System.IO.Compression.ZipFile]::CreateFromDirectory($tempDir, $zipPath, 'Optimal', $false);\n"

            "Write-Host '[3/3] 清理临时文件...';\n"
            "Remove-Item $tempDir -Recurse -Force;\n"

            "$sizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 1);\n"
            "Write-Host ('SIZE_MB=' + $sizeMB);\n"
        )
