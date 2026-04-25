//! Tauri IPC 命令 —— 前端通过 invoke 调用这些函数
//!
//! 这些命令暴露给 Vue3 前端，用于：
//!   - 查询后端端口
//!   - 查询后端状态
//!   - 重启后端
//!   - 打开外部浏览器

use crate::backend::BackendManager;
use tauri::{Manager, State};
use std::sync::Mutex;

/// 获取后端端口号（前端需要这个来构造 API 请求地址）
#[tauri::command]
pub fn get_backend_port(port: State<'_, Mutex<u16>>) -> Result<u16, String> {
    let p = port.lock().map_err(|e| e.to_string())?;
    Ok(*p)
}

/// 获取后端运行状态
#[tauri::command]
pub fn get_backend_status(
    manager: State<'_, Mutex<BackendManager>>,
) -> Result<BackendStatus, String> {
    let mgr = manager.lock().map_err(|e| e.to_string())?;
    Ok(BackendStatus {
        running: mgr.is_running(),
        port: mgr.get_port(),
    })
}

/// 重启后端
#[tauri::command]
pub async fn restart_backend(
    manager: State<'_, Mutex<BackendManager>>,
    port_state: State<'_, Mutex<u16>>,
) -> Result<u16, String> {
    // 先停旧的
    {
        let mgr = manager.lock().map_err(|e| e.to_string())?;
        mgr.terminate();
    }
    // 给一点时间释放端口
    tokio::time::sleep(std::time::Duration::from_secs(2)).await;

    // 再启动新的
    let mut mgr = manager.lock().map_err(|e| e.to_string())?;
    match mgr.start_and_wait(120) {
        Ok(new_port) => {
            *port_state.lock().unwrap() = new_port;
            Ok(new_port)
        }
        Err(e) => Err(e),
    }
}

/// 在系统浏览器中打开 URL
#[tauri::command]
pub fn open_in_browser(url: String) -> Result<(), String> {
    webbrowser::open(&url).map_err(|e| format!("打开浏览器失败: {}", e))
}

/// 运行安装流程
#[tauri::command]
pub fn run_installation(
    manager: State<'_, Mutex<BackendManager>>,
) -> Result<InstallationStatus, String> {
    let mgr = manager.lock().map_err(|e| e.to_string())?;
    
    // 检查是否需要安装
    let python_path = mgr.find_python();
    let needs_install = python_path.is_none();
    
    // 尝试提取内嵌 Python
    let embedded_extracted = if needs_install {
        if let Ok(resource_dir) = mgr._app_handle.path().resource_dir() {
            let zip_path = resource_dir.join("python-3.11.9-embed-amd64.zip");
            if zip_path.exists() {
                let target_python = mgr.project_root.join("tools/python_embed/python.exe");
                mgr.extract_python_from_zip(&zip_path, &target_python).is_ok()
            } else {
                false
            }
        } else {
            false
        }
    } else {
        true
    };
    
    Ok(InstallationStatus {
        needs_install: !embedded_extracted,
        python_available: python_path.is_some() || embedded_extracted,
        embedded_extracted,
        python_path: python_path.map(|p| p.to_string_lossy().to_string()),
    })
}

/// 检查环境状态
#[tauri::command]
pub fn check_environment(
    manager: State<'_, Mutex<BackendManager>>,
) -> Result<EnvironmentInfo, String> {
    let mgr = manager.lock().map_err(|e| e.to_string())?;
    
    let python_available = mgr.find_python().is_some();
    let has_embedded = {
        if let Ok(resource_dir) = mgr._app_handle.path().resource_dir() {
            resource_dir.join("python-3.11.9-embed-amd64.zip").exists() ||
            resource_dir.join("python_embed").exists()
        } else {
            false
        }
    };
    
    let project_root = mgr.project_root.to_string_lossy().to_string();
    
    Ok(EnvironmentInfo {
        python_available,
        has_embedded_python: has_embedded,
        project_root,
    })
}

/// 手动提取内嵌 Python
#[tauri::command]
pub fn extract_embedded_python(
    manager: State<'_, Mutex<BackendManager>>,
) -> Result<bool, String> {
    let mgr = manager.lock().map_err(|e| e.to_string())?;
    
    if let Ok(resource_dir) = mgr._app_handle.path().resource_dir() {
        let zip_path = resource_dir.join("python-3.11.9-embed-amd64.zip");
        let target_python = mgr.project_root.join("tools/python_embed/python.exe");
        
        if zip_path.exists() {
            match mgr.extract_python_from_zip(&zip_path, &target_python) {
                Ok(()) => Ok(true),
                Err(e) => Err(e),
            }
        } else {
            Err("未找到内嵌 Python zip 文件".to_string())
        }
    } else {
        Err("无法访问资源目录".to_string())
    }
}

/// 后端状态返回结构
#[derive(serde::Serialize, Clone)]
pub struct BackendStatus {
    running: bool,
    port: u16,
}

/// 安装状态返回结构
#[derive(serde::Serialize, Clone)]
pub struct InstallationStatus {
    needs_install: bool,
    python_available: bool,
    embedded_extracted: bool,
    python_path: Option<String>,
}

/// 环境信息返回结构
#[derive(serde::Serialize, Clone)]
pub struct EnvironmentInfo {
    python_available: bool,
    has_embedded_python: bool,
    project_root: String,
}
