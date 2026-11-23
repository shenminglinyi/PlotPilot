# PlotPilot 桌面版发布手册

本文记录 PlotPilot 的 Windows 与 macOS 发布能力。目标是让后续版本只需要升级版本号、验证、推送标签，CI 即可产出完整且可自动更新的 Release。

## 当前发布范围

| 平台 | 安装包 | 自动更新产物 | 清单键 |
| --- | --- | --- | --- |
| Windows x64 | `PlotPilot_<version>_x64-setup.exe` | 安装包本身 + `.sig` | `windows-x86_64`、`windows-x86_64-nsis` |
| macOS Apple Silicon | `PlotPilot_<version>_aarch64.dmg` | `PlotPilot_<version>_aarch64.app.tar.gz` + `.sig` | `darwin-aarch64`、`darwin-aarch64-app` |
| macOS Intel | `PlotPilot_<version>_x64.dmg` | `PlotPilot_<version>_x64.app.tar.gz` + `.sig` | `darwin-x86_64`、`darwin-x86_64-app` |

安装包、更新归档和 `latest.json` 均由 GitHub Releases 托管，不需要自建下载服务器，也不占用自有服务器带宽。

## 发布架构

发布入口是 `.github/workflows/release.yml`，由 `v*` 标签触发：

1. `prepare` 校验版本与签名 Secret，创建或复用 Draft Release。
2. `build` 在三个原生 runner 上并行构建冻结后端和 Tauri 包：
   - `windows-latest`：Windows x64 / NSIS；
   - `macos-latest`：Apple Silicon；
   - `macos-15-intel`：Intel Mac。
3. macOS 必须构建 `app,dmg`。`dmg` 是给用户安装的，`app` target 才会生成 updater 使用的 `.app.tar.gz` 和签名。
4. `publish` 下载 Draft 中的全部资产，由 `scripts/build_updater_manifest.py` 生成公开下载 URL，再由 `scripts/validate_updater_manifest.py` 校验版本、平台键、资产和签名。
5. 只有三个构建和最终校验全部成功，Release 才从 Draft 切换为 Latest。

这种设计保证单个平台失败时不会公开半成品，也避免并行 Tauri Action 争抢覆盖 `latest.json`。

## 密钥和 GitHub Secrets

Tauri updater 使用同一对 minisign 密钥为三个平台签名：

- 公钥保存在 `frontend/src-tauri/tauri.conf.json` 的 `plugins.updater.pubkey`；
- 私钥和密码不得进入仓库、日志或聊天；
- GitHub 仓库必须配置：
  - `TAURI_SIGNING_PRIVATE_KEY`
  - `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`

发布前可只检查 Secret 是否存在，不可读取其内容：

```powershell
gh secret list --repo shenminglinyi/PlotPilot
```

私钥文件和密码必须分别保存到密码管理器及加密离线备份。GitHub Secret 无法导出恢复。私钥丢失后只能轮换密钥，而旧客户端将无法自动升级到使用新密钥的版本。

## 标准发布流程

以下以 `4.8.2` 为例。

推荐先使用发布 CLI 完成版本同步、Secret/标签预检和本地最低验证：

```powershell
python scripts/release_desktop.py prepare 4.8.2
```

该命令只修改版本清单并运行检查，不会自动提交、推送、创建 worktree 或标签。涉及远端状态变更的步骤继续由维护者检查 diff 后显式执行。临时只检查版本与清单脚本时可加 `--skip-build`，正式发布不应跳过完整构建检查。

### 1. 准备并同步版本

用编辑器把根目录 `VERSION` 改为目标版本，然后执行：

```powershell
python scripts/sync_release_version.py
python scripts/sync_release_version.py --check
```

同步脚本会更新前端、Tauri、Cargo 和后端暴露的版本。不要只改 `package.json`。

以上两条底层命令已包含在 `release_desktop.py prepare` 中，保留在这里用于单独排错。

### 2. 本地验证

```powershell
python -m pytest tests/unit/scripts/test_updater_manifest.py -q
npm run build --prefix frontend
cargo fmt --manifest-path frontend/src-tauri/Cargo.toml -- --check
cargo check --manifest-path frontend/src-tauri/Cargo.toml
```

根据本次功能改动补充并运行相关测试。发布手册中的命令是最低检查集，不代替功能回归。

### 3. 提交开发仓库

仅暂存本次发布文件，保留工作区内用户的其它未提交改动：

```powershell
git add -- VERSION frontend/package.json frontend/package-lock.json `
  frontend/src-tauri/Cargo.toml frontend/src-tauri/Cargo.lock `
  frontend/src-tauri/tauri.conf.json interfaces/api/settings.py
git commit -m "release: prepare 4.8.2"
git push dev master
```

如果发布包含功能或工作流变更，将对应文件一并明确加入，不要使用无差别的 `git add -A`。

### 4. 同步公开仓库

本地 `dev` 与 `origin` 是两个不同历史的仓库，不能直接把开发分支整体强推到公开仓库。优先通过公开仓库 PR 合入；维护者在已获授权时也可以使用临时 worktree，把确认过的发布提交 cherry-pick 到 `origin/master`。

```powershell
git fetch origin master
$publicWorktree = Join-Path (Split-Path -Parent (Get-Location)) "Plotpilot-public-release"
git worktree add -b public-release-4.8.2 $publicWorktree origin/master
git -C $publicWorktree cherry-pick <release-commit>
git -C $publicWorktree push origin HEAD:master
```

推送前必须确认 worktree 干净、提交内容正确。发布结束后验证绝对路径和 `git status`，再用 `git worktree remove` 清理临时目录。

### 5. 创建并推送标签

标签必须指向公开仓库中包含目标版本的提交，且名称必须与 `VERSION` 完全一致：

```powershell
git -C $publicWorktree tag -a v4.8.2 -m "PlotPilot 4.8.2"
git -C $publicWorktree push origin v4.8.2
```

推送标签会自动启动 Release 工作流。可用以下命令查找并跟踪运行：

```powershell
gh run list --repo shenminglinyi/PlotPilot --workflow release.yml --limit 3
gh run watch <run-id> --repo shenminglinyi/PlotPilot --exit-status
```

## 发布后验证

发布完成后优先运行统一验证命令：

```powershell
python scripts/release_desktop.py verify 4.8.2
```

它会下载 Release 全部资产，逐项核对 GitHub SHA-256 digest，调用签名清单验证器，并检查公网 Latest 清单、三个更新下载和两个 DMG 的 HTTP 状态与内容类型。下面的命令用于人工复核或定位具体故障。

### Release 状态和资产

```powershell
gh release view v4.8.2 --repo shenminglinyi/PlotPilot `
  --json isDraft,isPrerelease,publishedAt,url,assets
```

必须满足：

- `isDraft` 和 `isPrerelease` 均为 `false`；
- 至少包含一个 Windows EXE、两个 DMG、两个 `.app.tar.gz`、三个 `.sig` 和 `latest.json`；
- 资产版本号和 Release 标签一致。

### 公网更新清单

```powershell
$url = "https://github.com/shenminglinyi/PlotPilot/releases/latest/download/latest.json?verify=$([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())"
$response = Invoke-WebRequest -UseBasicParsing -Uri $url
$manifest = [Text.Encoding]::UTF8.GetString([byte[]]$response.Content) | ConvertFrom-Json
$manifest.version
$manifest.platforms.PSObject.Properties.Name
```

版本应为新版本，平台项应有六个。三个唯一更新 URL（Windows、Mac ARM、Mac Intel）均应返回 HTTP 200 和 `application/octet-stream`。

## 失败恢复

### Release 保持 Draft

这是预期的安全行为。先查看失败日志：

```powershell
gh run view <run-id> --repo shenminglinyi/PlotPilot --log-failed
```

修复后重新触发。不要为了绕过验证手工把不完整 Draft 发布。

### Draft Release ID 返回 404

Draft 的网页地址通常是 `untagged-*`，不要调用按标签查询的 REST endpoint 获取 ID。使用：

```powershell
gh release view v4.8.2 --repo shenminglinyi/PlotPilot --json databaseId --jq .databaseId
```

### macOS 只有 DMG，没有 `.app.tar.gz`

macOS 构建参数必须包含：

```text
--bundles app,dmg
```

只构建 `dmg` 会出现“no updater-enabled targets were built”，无法形成稳定的 updater 归档。

### macOS runner 排队后被取消

若 job 的 `steps` 为空且结论为 `cancelled`，通常是 GitHub 没有分配到 Mac runner，不是代码失败。待同一运行结束后只重跑失败任务：

```powershell
gh run rerun <run-id> --repo shenminglinyi/PlotPilot --failed
```

### 可以移动或重建标签吗

仅当 Release 仍是 Draft、尚未对外发布时，才能在核实目标提交后删除并重建标签。Release 一旦公开，禁止移动同名标签；应修复问题并发布新的补丁版本。

### `latest.json` 指向 GitHub API 资产 URL

最终清单必须使用：

```text
https://github.com/<owner>/<repo>/releases/download/<tag>/<asset>
```

当前由 `build_updater_manifest.py` 生成并由验证脚本强制检查，不应手工接受 `api.github.com/repos/.../releases/assets/...` 地址。

## macOS 签名与公证

当前 macOS 使用 ad-hoc 签名（`signingIdentity: "-"`），能保证 Apple Silicon 应用具有代码签名，但不是 Apple Developer 公证。用户首次打开时可能需要在“系统设置 → 隐私与安全性”中允许。

若要消除 Gatekeeper 提示，需要 Apple Developer 会员、Developer ID Application 证书和公证凭据。引入正式签名时，应仅通过 GitHub Secrets 注入证书与密码，并在 CI 中增加 `codesign`、notarization 和 stapling 验证；不要把证书文件提交到仓库。

## 关键文件

| 文件 | 作用 |
| --- | --- |
| `.github/workflows/release.yml` | 三平台构建、Draft、验证与发布编排 |
| `VERSION` | 唯一发布版本源 |
| `scripts/sync_release_version.py` | 同步所有运行时版本 |
| `scripts/release_desktop.py` | 发布前准备与发布后公网一键验证 |
| `scripts/build_backend_pyinstaller.py` | 原生冻结 FastAPI 后端 |
| `scripts/build_updater_manifest.py` | 从 Release 资产生成多平台清单 |
| `scripts/validate_updater_manifest.py` | 校验平台项、公开 URL、资产和签名 |
| `frontend/src-tauri/tauri.conf.json` | bundle、updater 公钥和 macOS 签名配置 |
