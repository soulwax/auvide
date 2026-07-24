// auvide desktop — thin Rust backend over the Python engine.
// The pipeline is NOT reimplemented here: we build a recipe in the frontend,
// hand it to the auvide.cli engine (via the bundled `uv` sidecar), and stream
// its progress back as events.
pub mod bootstrap;
pub mod paths;
pub mod protocol;
pub mod query;
pub mod render;
pub mod runtime;

use std::path::{Path, PathBuf};
use std::process::Command;
use tauri::{AppHandle, Manager};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Locate the auvide engine package (dev: the monorepo's `engine/` dir, staged
/// into `src-tauri/engine/` by `beforeDevCommand`/`beforeBuildCommand`; bundled:
/// the same staged copy shipped as a Tauri resource). Only one copy of the
/// engine source exists in the repo — `../engine` — this just finds wherever
/// it landed for this run.
pub(crate) fn engine_dir(app: &AppHandle) -> PathBuf {
    if let Ok(res) = app.path().resource_dir() {
        let e = res.join("engine");
        if e.join("pyproject.toml").exists() {
            return e;
        }
    }
    // dev: staged copy beside the crate (see package.json's `stage-engine` script)
    let staged = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("engine");
    if staged.join("pyproject.toml").exists() {
        return staged;
    }
    // fallback: the monorepo engine/ directly (e.g. `cargo check` without a bun build)
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../engine")
}

#[cfg(all(target_os = "windows", target_arch = "x86_64"))]
const UV_SIDECAR_NAME: &str = "uv-x86_64-pc-windows-msvc.exe";
#[cfg(all(target_os = "macos", target_arch = "x86_64"))]
const UV_SIDECAR_NAME: &str = "uv-x86_64-apple-darwin";
#[cfg(all(target_os = "macos", target_arch = "aarch64"))]
const UV_SIDECAR_NAME: &str = "uv-aarch64-apple-darwin";
#[cfg(all(target_os = "linux", target_arch = "x86_64"))]
const UV_SIDECAR_NAME: &str = "uv-x86_64-unknown-linux-gnu";
#[cfg(not(any(
    all(target_os = "windows", target_arch = "x86_64"),
    all(target_os = "macos", target_arch = "x86_64"),
    all(target_os = "macos", target_arch = "aarch64"),
    all(target_os = "linux", target_arch = "x86_64")
)))]
const UV_SIDECAR_NAME: &str = "";

fn uv_sidecar_path(app: &AppHandle) -> Result<PathBuf, String> {
    if UV_SIDECAR_NAME.is_empty() {
        return Err("no bundled uv sidecar exists for this platform".into());
    }
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("binaries")
        .join(UV_SIDECAR_NAME);
    let mut candidates = vec![dev];
    if let Ok(resources) = app.path().resource_dir() {
        candidates.push(resources.join("binaries").join(UV_SIDECAR_NAME));
        candidates.push(resources.join(UV_SIDECAR_NAME));
    }
    candidates
        .into_iter()
        .find(|path| path.is_file())
        .ok_or_else(|| format!("bundled uv sidecar is unavailable: {UV_SIDECAR_NAME}"))
}

pub(crate) fn engine_cmd(app: &AppHandle, engine: &Path) -> Result<Command, String> {
    let paths = paths::AppPaths::from_app(app)?;
    let python = runtime::ensure_runtime(
        &paths,
        &uv_sidecar_path(app)?,
        engine,
        env!("CARGO_PKG_VERSION"),
    )?;
    let mut c = Command::new(python);
    c.args(["-m", "auvide.cli"]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(CREATE_NO_WINDOW);
    }
    Ok(c)
}

/// Styles / targets / knobs, straight from recipe.py (single source of truth).
#[tauri::command]
fn config(app: AppHandle) -> Result<serde_json::Value, String> {
    let engine = engine_dir(&app);
    let out = engine_cmd(&app, &engine)?
        .arg("--dump-config")
        .output()
        .map_err(|e| format!("failed to run managed engine: {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    serde_json::from_slice(&out.stdout).map_err(|e| e.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(render::RenderState::default())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            config,
            query::inspect_media,
            render::run_render,
            render::cancel_render
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::UV_SIDECAR_NAME;

    #[test]
    fn supported_targets_have_a_target_named_uv_sidecar() {
        assert!(!UV_SIDECAR_NAME.is_empty());
        assert!(UV_SIDECAR_NAME.starts_with("uv-"));
    }
}
