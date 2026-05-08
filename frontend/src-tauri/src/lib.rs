//! PlotPilot Tauri 主入口
//!
//! 架构概览：
//!   用户双击 exe → Tauri WebView 渲染 Vue3 前端
//!              → Rust 端自动查找/启动 Python FastAPI 后端
//!              → 前端通过 HTTP 请求后端 API（同 localhost）
//!
//! 核心设计原则：
//!   1. 零配置：用户不需要安装 Python、不需要命令行
//!   2. Sidecar 模式：Python 作为子进程被管理
//!   3. 动态端口：自动寻找可用端口，避免冲突
//!   4. 生产数据目录：release 构建向子进程注入 `AITEXT_PROD_DATA_DIR`（见 `application/paths.py`）
//!   5. Windows：子进程纳入 Job Object（KILL_ON_JOB_CLOSE），与 `Drop`/显式 terminate 双保险
//!   6. 关闭窗口：拦截 CloseRequested → 后端 HTTP 优雅停机 → 超时强杀 → `exit(0)`

mod backend;
mod commands;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, WindowEvent};
use backend::BackendManager;

/// 防止重复 spawn 多条优雅退出线程（用户连点关闭）
static GRACEFUL_SHUTDOWN_STARTED: AtomicBool = AtomicBool::new(false);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // 初始化日志
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info"))
        .init();

    log::info!("🚀 PlotPilot (墨枢) 启动中...");

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(win) = app.get_webview_window("main") {
                let _ = win.unminimize();
                let _ = win.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // 已经在关闭中，直接忽略后续点击
                if GRACEFUL_SHUTDOWN_STARTED.swap(true, Ordering::SeqCst) {
                    api.prevent_close();
                    return;
                }
                api.prevent_close();

                // 最小化窗口给用户反馈（关闭正在进行）
                let _ = window.minimize();

                let app_handle = window.app_handle().clone();
                std::thread::spawn(move || {
                    let backend = app_handle.state::<Mutex<BackendManager>>();
                    if let Ok(mgr) = backend.lock() {
                        // 减少超时时间，快速关闭
                        mgr.graceful_shutdown(Duration::from_secs(3));
                    }
                    app_handle.exit(0);
                });
            }
        })
        .setup(|app| {
            let handle = app.handle().clone();

            let manager = BackendManager::new(handle.clone());
            app.manage(std::sync::Mutex::new(manager));

            let app_handle = app.handle().clone();
            std::thread::spawn(move || {
                let backend = app_handle.state::<Mutex<BackendManager>>();
                let port = match backend.lock() {
                    Ok(mut mgr) => match mgr.spawn_only() {
                        Ok(p) => p,
                        Err(e) => {
                            log::error!("❌ 后端进程启动失败: {}", e);
                            return;
                        }
                    },
                    Err(e) => {
                        log::error!("后端管理器锁 poisoned: {}", e);
                        return;
                    }
                };

                match BackendManager::wait_for_ready(port, 120) {
                    Ok(()) => log::info!("✅ 后端已就绪，端口: {}", port),
                    Err(e) => log::error!(
                        "❌ 后端就绪超时或失败: {}（子进程端口 {}，请查 aitext 日志）",
                        e,
                        port
                    ),
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_backend_port,
            commands::get_backend_status,
            commands::restart_backend,
            commands::open_in_browser,
            commands::toggle_devtools,
            commands::run_installation,
            commands::check_environment,
            commands::extract_embedded_python,
        ])
        .run(tauri::generate_context!())
        .expect("error while running PlotPilot");
}
