# PlotPilot 图标

源图标使用至少 1024×1024 的方形 PNG。请在 `frontend/` 目录执行：

```bash
npm run tauri -- icon src-tauri/icons/icon-source-1024.png
```

Tauri 会生成各平台所需文件，包括：

- 32x32.png
- 128x128.png
- 128x128@2x.png (256x256)
- icon.icns (macOS)
- icon.ico (Windows)

不要单独手工缩放其中某个文件；更新源图标后应重新生成整套资源并检查 Windows、macOS 和托盘显示效果。
