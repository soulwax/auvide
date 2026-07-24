// auvide desktop — thin Rust backend over the Python engine.
// The pipeline is NOT reimplemented here: we build a recipe in the frontend,
// hand it to the auvide.cli engine (via `uv run -m auvide.cli`), and stream
// its progress back as events.
pub mod paths;
pub mod protocol;
pub mod runtime;

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::{AppHandle, Emitter, Manager, State};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Default, Clone)]
struct RenderState(Arc<Mutex<Option<u32>>>); // pid of the running engine, if any

/// Locate the auvide engine package (dev: the monorepo's `engine/` dir, staged
/// into `src-tauri/engine/` by `beforeDevCommand`/`beforeBuildCommand`; bundled:
/// the same staged copy shipped as a Tauri resource). Only one copy of the
/// engine source exists in the repo — `../engine` — this just finds wherever
/// it landed for this run.
fn engine_dir(app: &AppHandle) -> PathBuf {
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

fn uv_cmd(engine: &Path) -> Command {
    // uv provides Python + the auvide package (installed from `engine`) without
    // touching a system Python or an OneDrive-synced .venv.
    let mut c = Command::new("uv");
    c.args([
        "run",
        "--project",
        &engine.to_string_lossy(),
        "--python",
        "3.12",
        "-m",
        "auvide.cli",
    ]);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        c.creation_flags(CREATE_NO_WINDOW);
    }
    c
}

/// Styles / targets / knobs, straight from recipe.py (single source of truth).
#[tauri::command]
fn config(app: AppHandle) -> Result<serde_json::Value, String> {
    let engine = engine_dir(&app);
    let out = uv_cmd(&engine)
        .arg("--dump-config")
        .output()
        .map_err(|e| format!("failed to run engine (is `uv` on PATH?): {e}"))?;
    if !out.status.success() {
        return Err(String::from_utf8_lossy(&out.stderr).to_string());
    }
    serde_json::from_slice(&out.stdout).map_err(|e| e.to_string())
}

/// Start a render. `recipe` is the JSON recipe; input/output are explicit paths.
#[tauri::command]
fn run_render(
    app: AppHandle,
    state: State<RenderState>,
    input: String,
    output: String,
    recipe: serde_json::Value,
) -> Result<(), String> {
    if state.0.lock().unwrap().is_some() {
        return Err("a render is already running".into());
    }
    let engine = engine_dir(&app);
    // unique per-run filename: a fixed name would collide if two renders (or
    // two app instances) raced to write it before the child process reads it.
    let recipe_path =
        std::env::temp_dir().join(format!("auvide_recipe_{}.json", std::process::id()));
    std::fs::write(&recipe_path, serde_json::to_vec_pretty(&recipe).unwrap())
        .map_err(|e| e.to_string())?;

    let mut child = uv_cmd(&engine)
        .arg(&input)
        .args(["-o", &output])
        .arg("--recipe")
        .arg(&recipe_path)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| e.to_string())?;

    *state.0.lock().unwrap() = Some(child.id());
    let stdout = child.stdout.take().unwrap();
    let stderr = child.stderr.take().unwrap();

    // one reader thread per pipe -> "render:log" events
    for pipe in [
        Box::new(stdout) as Box<dyn std::io::Read + Send>,
        Box::new(stderr) as Box<dyn std::io::Read + Send>,
    ] {
        let a = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(pipe).lines().map_while(Result::ok) {
                let _ = a.emit("render:log", line);
            }
        });
    }

    // waiter thread -> "render:done"
    let a = app.clone();
    let st = state.0.clone();
    std::thread::spawn(move || {
        let code = child.wait().ok().and_then(|s| s.code()).unwrap_or(-1);
        *st.lock().unwrap() = None;
        let _ = std::fs::remove_file(&recipe_path);
        let _ = a.emit("render:done", code);
    });
    Ok(())
}

#[tauri::command]
fn cancel_render(state: State<RenderState>) {
    if let Some(pid) = *state.0.lock().unwrap() {
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            let _ = Command::new("taskkill")
                .args(["/PID", &pid.to_string(), "/T", "/F"])
                .creation_flags(CREATE_NO_WINDOW)
                .spawn();
        }
        #[cfg(not(windows))]
        {
            let _ = Command::new("kill").arg(pid.to_string()).spawn();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(RenderState::default())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![config, run_render, cancel_render])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
