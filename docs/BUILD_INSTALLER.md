# Windows 安装包（Tauri / NSIS）

## 仓库里需要知道的


| 项 | 说明 |
| --- | --- |
| **Tauri 源码** | `frontend/src-tauri/` **在仓库中**；**构建产物** `frontend/src-tauri/target/` 由 `.gitignore` 忽略，需本地 `cargo tauri build` 生成 |
| **命令** | `python scripts/build_installer.py`（若本机存在该脚本；部分环境可能被 `.gitignore` 排除，由发行维护者自备）。`--dev` 只到前端；`--clean` 清理后再构建（见下文「`--clean` 清理范围」）；`--skip-frozen-backend` 跳过 PyInstaller（需已有 exe） |
| **冻结后端**       | `python scripts/build_backend_pyinstaller.py`（或由 `build_installer` 步骤 4 调用）。产出：`out/tauri/plotpilot-backend/plotpilot-backend.exe`                               |
| **构建机 Python** | **推荐 Python 3.12**，在**专用 venv** 内执行：`pip install pyinstaller` 与 `pip install -r requirements-nsis.txt`。勿用混装过 `requirements-local.txt`（torch/faiss 等）的环境，否则 PyInstaller 会把重型依赖打进包，体积与耗时暴涨。 |
| **占位**         | `out/tauri/plotpilot-backend/.gitkeep` 已入库，便于未打冻结包时通过 Tauri 资源 glob 校验                                                                                           |
| **安装包路径**      | `frontend/src-tauri/target/release/bundle/nsis/*.exe`                                                                                                            |
| **运行时**        | Tauri 优先启动 `plotpilot-backend.exe`；若无则回退 `python -m uvicorn`（本地开发）                                                                                               |

## `--clean` 清理范围

执行 `python scripts/build_installer.py --clean` 时会删除或清空：

- `frontend/dist`
- `frontend/src-tauri/target`（Rust / Tauri 产物）
- `build/pyinstaller-backend`（PyInstaller 工作目录）
- `out/tauri/plotpilot-backend/` 内除 `.gitkeep` 以外的内容

**不会**删除 `frontend/node_modules`：在 Windows 上，原生扩展（如 `.node`）常被编辑器或安全软件占用，`rmtree` 易报「拒绝访问」；依赖仍通过既有 `node_modules` + 必要时手动 `npm install` 维护。

## NSIS 体积限制与常见失败

若冻结目录 `out/tauri/plotpilot-backend/` **解压后总体积过大**（例如全局 Python 里已安装 **torch / transformers** 等，被 PyInstaller 整包收集），`cargo tauri build` 在 **NSIS（`makensis`）** 阶段可能出现：

`Internal compiler error #12345: error mmapping file ... is out of range`

这与 NSIS 对**超大安装包**的常见限制有关（量级约 **2 GiB**）。**解决办法**仍是使用**仅含 `requirements-nsis.txt`** 的干净虚拟环境执行 `build_installer.py`，避免把重型 ML 栈打进安装包。脚本在步骤 4 结束后若检测到冻结目录超过约 **1.8 GiB** 会打印告警。

## 推荐：专用 venv（Python 3.12）一键全量构建

与日常开发的 `.venv` 分开，避免把本机其它包装进冻结后端：

```powershell
py -3.12 -m venv .venv-nsis
.\.venv-nsis\Scripts\activate
pip install -U pip
pip install pyinstaller
pip install -r requirements-nsis.txt
python scripts/build_installer.py --clean
```

仅重打冻结后端时，同样先 `activate` 该 venv，再执行 `python scripts/build_backend_pyinstaller.py`（可加 `--force`）。

## 手动构建

```bash
cd frontend
npm install
npm run build
npm run tauri build
```

直接 `tauri build` 前须已存在冻结目录 `out/tauri/plotpilot-backend/`（含 `plotpilot-backend.exe` 或至少 `.gitkeep` 占位）。