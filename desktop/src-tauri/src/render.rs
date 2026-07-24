//! Typed render-process supervision for the desktop application.
//!
//! The engine owns pipeline behavior. This module owns the desktop process
//! boundary: a durable per-run recipe/control directory, versioned progress
//! events on stdout, diagnostics on stderr, and cooperative cancellation.

use std::fs;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};

use crate::paths::AppPaths;
use crate::protocol::{
    parse_progress_line, ParsedProgressLine, ProgressEnvelope, ProgressEvent, PROTOCOL_NAME,
    PROTOCOL_VERSION,
};

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const CANCEL_GRACE: Duration = Duration::from_secs(8);

#[derive(Debug, Clone)]
struct ActiveRender {
    run_id: String,
    pid: u32,
    cancel_file: PathBuf,
    cancel_requested: bool,
}

#[derive(Default, Clone)]
pub struct RenderState(Arc<Mutex<Option<ActiveRender>>>);

#[derive(Debug, Clone, Serialize)]
pub struct RenderExited {
    pub run_id: String,
    pub exit_code: i32,
}

/// Launch a render and return the caller-supplied run ID. The frontend creates
/// that ID before invoking this command so it can accept progress immediately.
#[tauri::command(rename_all = "camelCase")]
pub fn run_render(
    app: AppHandle,
    state: State<'_, RenderState>,
    input: String,
    output: String,
    recipe: serde_json::Value,
    run_id: String,
) -> Result<String, String> {
    validate_run_id(&run_id)?;
    if state
        .0
        .lock()
        .map_err(|_| "render state lock poisoned")?
        .is_some()
    {
        return Err("a render is already running".into());
    }

    let paths = AppPaths::from_app(&app)?;
    paths.ensure_base_directories()?;
    let job_dir = paths.jobs_dir().join(&run_id);
    fs::create_dir_all(&job_dir)
        .map_err(|error| format!("could not create render job directory: {error}"))?;
    let recipe_path = job_dir.join("recipe.json");
    let cancel_file = job_dir.join("cancel.requested");
    let _ = fs::remove_file(&cancel_file);
    fs::write(
        &recipe_path,
        serde_json::to_vec_pretty(&recipe)
            .map_err(|error| format!("could not serialize render recipe: {error}"))?,
    )
    .map_err(|error| format!("could not write render recipe: {error}"))?;

    let engine = crate::engine_dir(&app);
    let mut child = crate::engine_cmd(&app, &engine)?
        .arg(&input)
        .args(["-o", &output])
        .arg("--recipe")
        .arg(&recipe_path)
        .args(["--progress-json", "--run-id", &run_id, "--cancel-file"])
        .arg(&cancel_file)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| format!("could not start render: {error}"))?;

    let active = ActiveRender {
        run_id: run_id.clone(),
        pid: child.id(),
        cancel_file: cancel_file.clone(),
        cancel_requested: false,
    };
    *state.0.lock().map_err(|_| "render state lock poisoned")? = Some(active);
    let response_run_id = run_id.clone();

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "render stdout was not captured".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "render stderr was not captured".to_string())?;
    let protocol_failed = Arc::new(AtomicBool::new(false));

    let stdout_app = app.clone();
    let stdout_run_id = run_id.clone();
    let stdout_protocol_failed = protocol_failed.clone();
    let stdout_reader = std::thread::spawn(move || {
        for line in BufReader::new(stdout).lines() {
            let line = match line {
                Ok(line) => line,
                Err(error) => {
                    report_protocol_failure(
                        &stdout_app,
                        &stdout_run_id,
                        &stdout_protocol_failed,
                        format!("could not read render progress: {error}"),
                    );
                    break;
                }
            };
            match parse_progress_line(&line) {
                Ok(ParsedProgressLine::Known(event)) => {
                    let _ = stdout_app.emit("render:progress", event);
                }
                Ok(ParsedProgressLine::Unknown { event_type, .. }) => {
                    let _ = stdout_app.emit(
                        "render:log",
                        format!("[protocol] ignored unsupported event type: {event_type}"),
                    );
                }
                Err(error) => report_protocol_failure(
                    &stdout_app,
                    &stdout_run_id,
                    &stdout_protocol_failed,
                    format!("invalid render progress protocol: {error}"),
                ),
            }
        }
    });

    let stderr_app = app.clone();
    let stderr_reader = std::thread::spawn(move || {
        for line in BufReader::new(stderr).lines().map_while(Result::ok) {
            let _ = stderr_app.emit("render:log", line);
        }
    });

    let waiter_app = app.clone();
    let waiter_state = state.0.clone();
    std::thread::spawn(move || {
        let process_exit = child
            .wait()
            .ok()
            .and_then(|status| status.code())
            .unwrap_or(-1);
        let _ = stdout_reader.join();
        let _ = stderr_reader.join();
        let exit_code = if protocol_failed.load(Ordering::Relaxed) {
            1
        } else {
            process_exit
        };

        if let Ok(mut active) = waiter_state.lock() {
            if active
                .as_ref()
                .is_some_and(|render| render.run_id == run_id)
            {
                *active = None;
            }
        }
        if exit_code == 0 {
            let _ = fs::remove_file(&cancel_file);
        }
        let _ = waiter_app.emit("render:exited", RenderExited { run_id, exit_code });
    });

    Ok(response_run_id)
}

/// Ask the engine to stop at its next safe checkpoint, then force-stop only if
/// it does not exit during the grace interval.
#[tauri::command]
pub fn cancel_render(state: State<'_, RenderState>) -> Result<(), String> {
    let active = {
        let mut current = state.0.lock().map_err(|_| "render state lock poisoned")?;
        let render = current
            .as_mut()
            .ok_or_else(|| "no render is currently running".to_string())?;
        if render.cancel_requested {
            return Ok(());
        }
        fs::write(&render.cancel_file, b"")
            .map_err(|error| format!("could not request render cancellation: {error}"))?;
        render.cancel_requested = true;
        render.clone()
    };

    let state = state.0.clone();
    std::thread::spawn(move || {
        std::thread::sleep(CANCEL_GRACE);
        let should_force_stop = state
            .lock()
            .ok()
            .and_then(|current| current.clone())
            .is_some_and(|current| current.run_id == active.run_id && current.cancel_requested);
        if should_force_stop {
            force_stop(active.pid);
        }
    });
    Ok(())
}

fn report_protocol_failure(
    app: &AppHandle,
    run_id: &str,
    protocol_failed: &AtomicBool,
    message: String,
) {
    if protocol_failed.swap(true, Ordering::Relaxed) {
        return;
    }
    let _ = app.emit("render:log", format!("[protocol] {message}"));
    let _ = app.emit(
        "render:progress",
        ProgressEnvelope {
            protocol: PROTOCOL_NAME.into(),
            version: PROTOCOL_VERSION,
            run_id: run_id.into(),
            event: ProgressEvent::Failed {
                code: "invalid_progress_protocol".into(),
                message,
            },
        },
    );
}

fn validate_run_id(run_id: &str) -> Result<(), String> {
    if run_id.is_empty()
        || run_id.len() > 128
        || !run_id
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_')
    {
        return Err("render run ID must use only letters, numbers, '-' or '_'".into());
    }
    Ok(())
}

fn force_stop(pid: u32) {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn();
    }
    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .spawn();
    }
}

#[cfg(test)]
mod tests {
    use super::validate_run_id;

    #[test]
    fn accepts_safe_run_ids() {
        assert!(validate_run_id("4f08b4e9-3bae-4f58-a7e2-0c8d0d540770").is_ok());
        assert!(validate_run_id("desktop_run_42").is_ok());
    }

    #[test]
    fn rejects_unsafe_run_ids() {
        assert!(validate_run_id("").is_err());
        assert!(validate_run_id("../escape").is_err());
        assert!(validate_run_id("render id").is_err());
    }
}
