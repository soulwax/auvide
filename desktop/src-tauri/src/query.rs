//! Read-only typed queries against the managed auvide engine.

use std::path::Path;

use tauri::AppHandle;

/// Inspect source metadata through the engine-owned `auvide.media` contract.
#[tauri::command(rename_all = "camelCase")]
pub fn inspect_media(app: AppHandle, input: String) -> Result<serde_json::Value, String> {
    query_json(&app, &[input.as_str(), "--inspect-json"])
}

fn query_json(app: &AppHandle, arguments: &[&str]) -> Result<serde_json::Value, String> {
    let engine = crate::engine_dir(app);
    let output = crate::engine_cmd(app, Path::new(&engine))?
        .args(arguments)
        .output()
        .map_err(|error| format!("could not run managed engine query: {error}"))?;
    decode_engine_json(
        output.status.success(),
        &String::from_utf8_lossy(&output.stdout),
        &String::from_utf8_lossy(&output.stderr),
    )
}

fn decode_engine_json(
    success: bool,
    stdout: &str,
    stderr: &str,
) -> Result<serde_json::Value, String> {
    if !success {
        let detail = stderr.trim();
        return Err(if detail.is_empty() {
            "engine query failed without diagnostics".into()
        } else {
            detail.into()
        });
    }
    serde_json::from_str(stdout)
        .map_err(|error| format!("engine query returned invalid JSON: {error}"))
}

#[cfg(test)]
mod tests {
    use super::decode_engine_json;

    #[test]
    fn parses_successful_engine_json() {
        let value = decode_engine_json(true, r#"{"schema":"auvide.media"}"#, "").unwrap();
        assert_eq!(value["schema"], "auvide.media");
    }

    #[test]
    fn preserves_engine_diagnostics_on_failure() {
        assert_eq!(
            decode_engine_json(false, "", "ffprobe is missing\n").unwrap_err(),
            "ffprobe is missing"
        );
    }

    #[test]
    fn rejects_non_json_success_output() {
        assert!(decode_engine_json(true, "not json", "").is_err());
    }
}
