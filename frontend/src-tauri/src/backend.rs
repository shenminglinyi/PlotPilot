//! FastAPI 后端进程管理器
//!
//! 职责：
//!   1. 优先启动 PyInstaller 冻结产物 `plotpilot-backend.exe`（发布推荐）
//!   2. 否则回退：内嵌 / venv / 系统 Python + `python -m uvicorn`（开发）
//!   3. 健康检查轮询，等待 HTTP 就绪
//!   4. 管理子进程生命周期（退出时自动清理）

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Manager};
use ureq::Agent;

#[cfg(target_os = "windows")]
use std::os::windows::io::AsRawHandle;
#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;
#[cfg(target_os = "windows")]
use win32job::Job;

/// 后端管理器
pub struct BackendManager {
    /// 预留：后续若需从 Rust 侧发事件到前端会用到
    pub(crate) _app_handle: AppHandle,
    child: Mutex<Option<Child>>,
    port: Mutex<u16>,
    pub(crate) project_root: PathBuf,
    /// Windows：子进程纳入 Job，句柄关闭时随 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE 一并结束
    #[cfg(target_os = "windows")]
    job_kill_tree: Mutex<Option<Job>>,
}

impl BackendManager {
    pub fn new(app_handle: AppHandle) -> Self {
        // 确定项目根目录（Tauri exe 所在位置的上级或 resource 目录）
        let project_root = Self::detect_project_root(&app_handle);

        Self {
            _app_handle: app_handle,
            child: Mutex::new(None),
            port: Mutex::new(0),
            project_root,
            #[cfg(target_os = "windows")]
            job_kill_tree: Mutex::new(None),
        }
    }

    /// 是否在启动 Python 时注入 AITEXT_PROD_DATA_DIR（release 默认开启；debug 需设 AITEXT_FORCE_PROD_DATA=1）
    fn should_inject_prod_data_dir() -> bool {
        if cfg!(debug_assertions) {
            std::env::var("AITEXT_FORCE_PROD_DATA")
                .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
                .unwrap_or(false)
        } else {
            true
        }
    }

    /// Tauri 2：用户可写应用数据目录下的 `data/`（与 Python `application/paths.py` 约定一致）
    fn resolve_prod_data_dir(handle: &AppHandle) -> Result<PathBuf, String> {
        let base = handle
            .path()
            .app_data_dir()
            .map_err(|e| format!("无法解析 app_data_dir: {}", e))?;
        let data = base.join("data");
        std::fs::create_dir_all(&data)
            .map_err(|e| format!("无法创建数据目录 {}: {}", data.display(), e))?;
        Ok(data)
    }

    fn inject_prod_data_env(cmd: &mut Command, handle: &AppHandle) -> Result<(), String> {
        if !Self::should_inject_prod_data_dir() {
            return Ok(());
        }
        let path = Self::resolve_prod_data_dir(handle)?;
        log::info!(
            "📁 注入 {}={}",
            "AITEXT_PROD_DATA_DIR",
            path.display()
        );
        cmd.env("AITEXT_PROD_DATA_DIR", path.as_os_str());

        let logs_dir = path.join("logs");
        std::fs::create_dir_all(&logs_dir)
            .map_err(|e| format!("无法创建日志目录 {}: {}", logs_dir.display(), e))?;
        let log_file = logs_dir.join("aitext.log");
        cmd.env("LOG_FILE", log_file.as_os_str());

        Ok(())
    }

    /// PyInstaller onedir：`$RESOURCE/plotpilot-backend/plotpilot-backend.exe`（见 tauri.conf resources 映射）
    fn find_frozen_backend_exe(handle: &AppHandle) -> Option<PathBuf> {
        // 方案 1a：与 bundle.resources 映射一致（推荐；安装包与 tauri build 均可用）
        if let Ok(p) = handle.path().resolve(
            "plotpilot-backend/plotpilot-backend.exe",
            BaseDirectory::Resource,
        ) {
            if p.is_file() {
                log::info!("📦 后端路径 (resolve Resource): {}", p.display());
                return Some(p);
            }
        }

        // 方案 1b：旧配置曾用数组 + `../**/*`，打包后实际路径经 Tauri 归一化；用同一字符串解析
        if let Ok(p) = handle.path().resolve(
            "../../out/tauri/plotpilot-backend/plotpilot-backend.exe",
            BaseDirectory::Resource,
        ) {
            if p.is_file() {
                log::info!("📦 后端路径 (resolve legacy rel): {}", p.display());
                return Some(p);
            }
        }

        // 方案 1c：resource_dir 下直接探测（手工拷贝或扁平布局）
        if let Ok(rd) = handle.path().resource_dir() {
            let nested = rd.join("plotpilot-backend").join("plotpilot-backend.exe");
            if nested.is_file() {
                log::info!("📦 后端路径 (resource_dir nested): {}", nested.display());
                return Some(nested);
            }
            let flat = rd.join("plotpilot-backend.exe");
            if flat.is_file() {
                log::info!("📦 后端路径 (resource_dir flat): {}", flat.display());
                return Some(flat);
            }
        }

        // 方案 2：从 exe 父目录逐级向上找 out/tauri/...（裸 cargo build / 未拷贝 resources 时）
        if let Some(exe_path) = std::env::current_exe().ok().and_then(|p| p.canonicalize().ok()) {
            let mut dir = exe_path.parent().map(PathBuf::from);
            for _ in 0..32 {
                let Some(ref d) = dir else { break };
                let candidate = d
                    .join("out")
                    .join("tauri")
                    .join("plotpilot-backend")
                    .join("plotpilot-backend.exe");
                if candidate.is_file() {
                    log::info!("📦 后端路径 (dev walk-up): {}", candidate.display());
                    return Some(candidate);
                }
                dir = d.parent().map(PathBuf::from);
            }

            // 方案 3：与 plotpilot.exe 同目录下的 plotpilot-backend/（便携解压布局）
            if let Some(parent) = exe_path.parent() {
                let sibling = parent
                    .join("plotpilot-backend")
                    .join("plotpilot-backend.exe");
                if sibling.is_file() {
                    log::info!("📦 后端路径 (sibling dir): {}", sibling.display());
                    return Some(sibling);
                }
            }
        }

        None
    }

    /// 检测项目根目录（松散源码）或资源根（仅冻结后端时无 main.py）
    fn detect_project_root(handle: &AppHandle) -> PathBuf {
        if let Ok(resource_dir) = handle.path().resource_dir() {
            if Self::find_frozen_backend_exe(handle).is_some() {
                log::info!("📂 资源根目录（冻结后端）: {}", resource_dir.display());
                return resource_dir;
            }
            for candidate in [
                resource_dir.join("../../../"),
                resource_dir.join("../../"),
                resource_dir.clone(),
            ] {
                if candidate.join("interfaces/main.py").exists() {
                    log::info!("📂 项目根目录: {}", candidate.display());
                    return candidate.canonicalize().unwrap_or(candidate);
                }
            }
        }

        handle
            .path()
            .resource_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
    }

    /// 从指定端口开始，找到一个可用端口
    fn pick_free_port(start: u16) -> Option<u16> {
        (start..start + 100).find(|&port| {
            std::net::TcpListener::bind(("127.0.0.1", port)).is_ok()
        })
    }

    /// 查找 Python 解释器，优先使用内嵌 Python
    pub(crate) fn find_python(&self) -> Option<PathBuf> {
        // 优先级：已解压的内嵌 Python > 资源目录中的内嵌 Python > 虚拟环境 > 系统 PATH

        // 1) 检查项目目录下的内嵌 Python
        let embedded = self.project_root.join("tools/python_embed/python.exe");
        if embedded.exists() {
            log::info!("🐍 使用项目目录下内嵌 Python: {}", embedded.display());
            return Some(embedded);
        }

        // 2) 尝试从资源目录获取内嵌 Python
        if let Ok(resource_dir) = self._app_handle.path().resource_dir() {
            let resource_python = resource_dir.join("python_embed/python.exe");
            if resource_python.exists() {
                // 复制到项目目录
                if let Err(e) = self.extract_embedded_python(&resource_dir) {
                    log::warn!("从资源目录提取内嵌 Python 失败: {}", e);
                } else {
                    if embedded.exists() {
                        log::info!("🐍 使用资源目录内嵌 Python: {}", embedded.display());
                        return Some(embedded);
                    }
                }
            }
        }

        // 3) 尝试从资源目录的 zip 解压
        if let Ok(resource_dir) = self._app_handle.path().resource_dir() {
            let zip_path = resource_dir.join("python-3.11.9-embed-amd64.zip");
            if zip_path.exists() {
                log::info!("📦 发现内嵌 Python zip，正在解压...");
                if let Err(e) = self.extract_python_from_zip(&zip_path, &embedded) {
                    log::warn!("解压内嵌 Python 失败: {}", e);
                } else {
                    if embedded.exists() {
                        log::info!("🐍 使用内嵌 Python (从zip解压): {}", embedded.display());
                        return Some(embedded);
                    }
                }
            }
        }

        // 4) 虚拟环境
        let venv = self.project_root.join(".venv/Scripts/python.exe");
        if venv.exists() {
            log::info!("🐍 使用虚拟环境 Python: {}", venv.display());
            return Some(venv);
        }

        // 5) 系统 PATH
        if let Ok(path) = which::which("python") {
            log::info!("🐍 使用系统 Python: {}", path.display());
            return Some(path);
        }
        if let Ok(path) = which::which("python3") {
            log::info!("🐍 使用系统 python3: {}", path.display());
            return Some(path);
        }

        None
    }

    /// 启动后端并等待就绪（重启后端等需在同一线程内连续完成的场景）
    pub fn start_and_wait(&mut self, timeout_secs: u64) -> Result<u16, String> {
        let port = self.spawn_only()?;
        Self::wait_for_ready(port, timeout_secs)?;
        Ok(port)
    }

    /// 仅启动子进程并写入端口（快速返回，不阻塞健康检查）。
    /// 用于在独立线程中先释放 `Mutex<BackendManager>`，避免与关窗逻辑长时间争锁。
    pub fn spawn_only(&mut self) -> Result<u16, String> {
        let port = Self::pick_free_port(8005).ok_or("无法分配空闲端口")?;
        log::info!("🔌 分配端口: {}", port);

        let frozen = Self::find_frozen_backend_exe(&self._app_handle);

        match &frozen {
            Some(p) => eprintln!("[DEBUG] ✅ 找到冻结后端: {}", p.display()),
            None => eprintln!("[DEBUG] ❌ 未找到冻结后端！将尝试 Python 解释器路线"),
        }

        let mut cmd = if let Some(ref exe) = frozen {
            let work_dir = exe
                .parent()
                .ok_or_else(|| "冻结后端路径无效".to_string())?;
            log::info!("📦 启动冻结后端: {}", exe.display());
            let mut c = Command::new(exe);
            c.arg(port.to_string())
                .current_dir(work_dir)
                .env("HF_HUB_OFFLINE", "1")
                .env("TRANSFORMERS_OFFLINE", "1")
                .env("HF_DATASETS_OFFLINE", "1")
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
            #[cfg(target_os = "windows")]
            {
                c.creation_flags(windows_subsystem_flag());
            }
            c
        } else {
            let python = self.find_python().ok_or_else(|| {
                "未找到 plotpilot-backend.exe，也未找到 Python。发布构建请运行 scripts/build_backend_pyinstaller.py；开发请安装 Python 3.10+".to_string()
            })?;
            log::info!("🐍 启动 uvicorn（解释器）: {}", python.display());
            let mut c = Command::new(&python);
            c.arg("-m")
                .arg("uvicorn")
                .arg("interfaces.main:app")
                .arg("--host")
                .arg("127.0.0.1")
                .arg("--port")
                .arg(port.to_string())
                .arg("--log-level")
                .arg("info")
                .current_dir(&self.project_root)
                .env("PYTHONIOENCODING", "utf-8")
                .env("PYTHONUNBUFFERED", "1")
                .env("HF_HUB_OFFLINE", "1")
                .env("TRANSFORMERS_OFFLINE", "1")
                .env("HF_DATASETS_OFFLINE", "1")
                .stdout(Stdio::piped())
                .stderr(Stdio::piped());
            #[cfg(target_os = "windows")]
            {
                c.creation_flags(windows_subsystem_flag());
            }
            c
        };

        Self::inject_prod_data_env(&mut cmd, &self._app_handle)?;

        let child = cmd
            .spawn()
            .map_err(|e| format!("启动后端失败: {}", e))?;

        #[cfg(target_os = "windows")]
        {
            let job = Job::create().map_err(|e| format!("创建 Job Object 失败: {}", e))?;
            let mut info = job
                .query_extended_limit_info()
                .map_err(|e| format!("Job 查询限制信息失败: {}", e))?;
            info.limit_kill_on_job_close();
            job.set_extended_limit_info(&mut info)
                .map_err(|e| format!("Job 设置限制失败: {}", e))?;
            let h = child.as_raw_handle() as isize;
            job.assign_process(h)
                .map_err(|e| format!("Job 绑定子进程失败: {}", e))?;
            *self.job_kill_tree.lock().unwrap() = Some(job);
            log::info!("🔗 已将后端子进程纳入 Job（KILL_ON_JOB_CLOSE）");
        }

        let pid = child.id();
        log::info!("▶️  后端子进程已启动 (PID={})", pid);

        *self.child.lock().unwrap() = Some(child);
        *self.port.lock().unwrap() = port;

        Ok(port)
    }

    /// 轮询等待后端就绪（不持有 `BackendManager` 的独占锁，可与关窗路径并行）
    pub fn wait_for_ready(port: u16, timeout_secs: u64) -> Result<(), String> {
        let health_url = format!("http://127.0.0.1:{}/health", port);
        let deadline = std::time::Instant::now() + Duration::from_secs(timeout_secs);

        // 第一阶段：等端口监听
        log::info!("⏳ 等待后端端口 {} 监听...", port);
        loop {
            if std::time::Instant::now() > deadline {
                return Err(format!("超时：后端在 {}s 内未开始监听端口", timeout_secs));
            }
            if Self::is_port_listening(port) {
                break;
            }
            thread::sleep(Duration::from_millis(400));
        }

        // 第二阶段：等 HTTP 响应（ureq 3：超时在 Agent 上配置）
        log::info!("⏳ 等待 HTTP 健康检查...");
        let agent: Agent = Agent::config_builder()
            .timeout_global(Some(Duration::from_secs(2)))
            .build()
            .into();
        loop {
            if std::time::Instant::now() > deadline {
                return Err(format!(
                    "超时：端口已监听但 HTTP 无响应 ({}s)",
                    timeout_secs
                ));
            }

            match agent.get(&health_url).call() {
                Ok(resp) if resp.status().as_u16() == 200 => {
                    log::info!("✅ 后端健康检查通过！");
                    return Ok(());
                }
                _ => {
                    thread::sleep(Duration::from_millis(400));
                }
            }
        }
    }

    /// 检查端口是否在监听
    fn is_port_listening(port: u16) -> bool {
        std::net::TcpStream::connect_timeout(
            &format!("127.0.0.1:{}", port).parse().unwrap(),
            Duration::from_millis(300),
        )
        .is_ok()
    }

    /// 获取当前端口号
    pub fn get_port(&self) -> u16 {
        *self.port.lock().unwrap()
    }

    /// 获取运行状态
    pub fn is_running(&self) -> bool {
        let mut guard = self.child.lock().unwrap();
        match guard.as_mut() {
            None => false,
            Some(child) => match child.try_wait() {
                Ok(None) => true,      // 还在运行
                Ok(Some(_)) => false, // 已退出
                Err(_) => true,       // 无法判断，假设还在运行
            },
        }
    }

    /// 从资源目录提取内嵌 Python
    fn extract_embedded_python(&self, resource_dir: &PathBuf) -> Result<(), String> {
        let source_dir = resource_dir.join("python_embed");
        let target_dir = self.project_root.join("tools/python_embed");
        
        log::info!("📂 从资源目录复制内嵌 Python: {} -> {}", source_dir.display(), target_dir.display());
        
        // 确保目标目录存在
        if let Some(parent) = target_dir.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("创建目录失败: {}", e))?;
        }
        
        // 复制整个目录
        self.copy_directory(&source_dir, &target_dir)?;
        
        Ok(())
    }

    /// 从 zip 文件解压内嵌 Python
    pub(crate) fn extract_python_from_zip(
        &self,
        zip_path: &PathBuf,
        target_python: &PathBuf,
    ) -> Result<(), String> {
        log::info!("📦 从 zip 解压内嵌 Python: {}", zip_path.display());
        
        // 确保目标目录存在
        let target_dir = target_python.parent().unwrap();
        if let Some(parent) = target_dir.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("创建目录失败: {}", e))?;
        }
        
        // 解压 zip 文件
        let zip_content = std::fs::read(zip_path)
            .map_err(|e| format!("读取 zip 文件失败: {}", e))?;
        
        let mut archive = zip::ZipArchive::new(std::io::Cursor::new(zip_content))
            .map_err(|e| format!("打开 zip 文件失败: {}", e))?;
        
        for i in 0..archive.len() {
            let mut file = archive.by_index(i)
                .map_err(|e| format!("读取 zip 条目失败: {}", e))?;
            
            if file.is_dir() {
                continue;
            }
            
            let outpath = target_dir.join(file.name());
            if let Some(parent) = outpath.parent() {
                std::fs::create_dir_all(parent)
                    .map_err(|e| format!("创建目录失败: {}", e))?;
            }
            
            let mut outfile = std::fs::File::create(&outpath)
                .map_err(|e| format!("创建文件失败: {}", e))?;
            
            std::io::copy(&mut file, &mut outfile)
                .map_err(|e| format!("复制文件内容失败: {}", e))?;
        }
        
        log::info!("✅ 内嵌 Python 解压完成");
        Ok(())
    }

    /// 递归复制目录
    fn copy_directory(&self, src: &PathBuf, dst: &PathBuf) -> Result<(), String> {
        if !src.exists() {
            return Err(format!("源目录不存在: {}", src.display()));
        }
        
        std::fs::create_dir_all(dst).map_err(|e| format!("创建目标目录失败: {}", e))?;
        
        for entry in std::fs::read_dir(src).map_err(|e| format!("读取源目录失败: {}", e))? {
            let entry = entry.map_err(|e| format!("读取目录条目失败: {}", e))?;
            let ty = entry.file_type().map_err(|e| format!("获取文件类型失败: {}", e))?;
            let src_path = entry.path();
            let dst_path = dst.join(entry.file_name());
            
            if ty.is_dir() {
                self.copy_directory(&src_path, &dst_path)?;
            } else {
                std::fs::copy(&src_path, &dst_path)
                    .map_err(|e| format!("复制文件失败 {} -> {}: {}", src_path.display(), dst_path.display(), e))?;
            }
        }
        
        Ok(())
    }

    /// 优雅关闭：先 POST `/internal/shutdown`，等待子进程退出；超时后 [`Self::terminate`]。
    pub fn graceful_shutdown(&self, timeout: Duration) {
        let port = *self.port.lock().unwrap();
        if port > 0 && self.is_running() {
            let url = format!("http://127.0.0.1:{}/internal/shutdown", port);
            let agent: Agent = Agent::config_builder()
                .timeout_global(Some(Duration::from_secs(2)))
                .build()
                .into();
            match agent.post(&url).send_empty() {
                Ok(resp) => {
                    log::info!(
                        "📤 已请求后端优雅关闭 (HTTP {})",
                        resp.status().as_u16()
                    );
                }
                Err(e) => {
                    log::warn!("优雅关闭 POST 失败（将等待超时后强杀）: {}", e);
                }
            }
        } else {
            log::info!("跳过后端优雅关闭（未运行或未分配端口）");
        }

        let deadline = Instant::now() + timeout;
        loop {
            {
                let mut guard = self.child.lock().unwrap();
                match guard.as_mut() {
                    None => {
                        log::info!("后端子进程已释放");
                        return;
                    }
                    Some(child) => match child.try_wait() {
                        Ok(Some(status)) => {
                            log::info!("✅ 后端已退出: {:?}", status);
                            guard.take();
                            return;
                        }
                        Ok(None) => {}
                        Err(e) => log::warn!("try_wait: {}", e),
                    },
                }
            }
            if Instant::now() > deadline {
                break;
            }
            thread::sleep(Duration::from_millis(50));
        }

        log::warn!("优雅关闭超时，执行强杀");
        self.terminate_hard();
    }

    fn terminate_hard(&self) {
        #[cfg(target_os = "windows")]
        {
            // 方法1: 使用 Job Object 杀死进程树
            let job = self.job_kill_tree.lock().unwrap().take();
            drop(job);

            // 方法2: 使用 taskkill 强制杀死整个进程树（双保险）
            let guard = self.child.lock().unwrap();
            if let Some(child) = guard.as_ref() {
                let pid = child.id();
                log::info!("🛑 使用 taskkill 强制终止进程树 (PID={})...", pid);

                // /F 强制终止 /T 包含子进程
                let kill_result = Command::new("taskkill")
                    .args(["/F", "/T", "/PID", &pid.to_string()])
                    .output();

                match kill_result {
                    Ok(output) => {
                        if output.status.success() {
                            log::info!("✅ taskkill 成功终止进程树");
                        } else {
                            log::warn!(
                                "taskkill 返回非零状态: {}",
                                String::from_utf8_lossy(&output.stderr)
                            );
                        }
                    }
                    Err(e) => {
                        log::warn!("taskkill 执行失败: {}", e);
                    }
                }
            }
        }

        let mut guard = self.child.lock().unwrap();
        if let Some(mut child) = guard.take() {
            log::info!("🛑 正在强杀后端进程...");
            let _ = child.kill();
            let _ = child.wait();
            log::info!("✅ 后端进程已终止");
        }
    }

    /// 立即强杀子进程（重启后端等场景）。
    pub fn terminate(&self) {
        self.terminate_hard();
    }
}

impl Drop for BackendManager {
    fn drop(&mut self) {
        self.terminate_hard();
    }
}

/// Windows 上隐藏子进程控制台窗口的 flag
#[cfg(target_os = "windows")]
fn windows_subsystem_flag() -> u32 {
    const CREATE_NO_WINDOW: u32 = 0x08000000;
    CREATE_NO_WINDOW
}

#[cfg(not(target_os = "windows"))]
fn windows_subsystem_flag() -> u32 {
    0
}
