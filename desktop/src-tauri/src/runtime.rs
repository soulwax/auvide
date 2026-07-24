//! Serializable state transitions for the desktop-managed Python runtime.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use serde::{Deserialize, Serialize};

use crate::paths::AppPaths;

pub const STATE_SCHEMA_VERSION: u32 = 1;
pub const PYTHON_VERSION: &str = "3.12";
pub const PILLOW_VERSION: &str = "11.3.0";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeStatus {
    Missing,
    Installing,
    Ready,
    Broken,
    UpgradeRequired,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeState {
    pub schema_version: u32,
    pub status: RuntimeStatus,
    pub engine_version: String,
    pub python_version: Option<String>,
    pub venv_path: Option<PathBuf>,
    pub installed_packages: BTreeMap<String, String>,
    pub detail: Option<String>,
}

impl RuntimeState {
    pub fn missing(engine_version: impl Into<String>) -> Self {
        Self {
            schema_version: STATE_SCHEMA_VERSION,
            status: RuntimeStatus::Missing,
            engine_version: engine_version.into(),
            python_version: None,
            venv_path: None,
            installed_packages: BTreeMap::new(),
            detail: None,
        }
    }

    pub fn ready(
        engine_version: impl Into<String>,
        python_version: impl Into<String>,
        venv_path: PathBuf,
    ) -> Self {
        Self {
            schema_version: STATE_SCHEMA_VERSION,
            status: RuntimeStatus::Ready,
            engine_version: engine_version.into(),
            python_version: Some(python_version.into()),
            venv_path: Some(venv_path),
            installed_packages: BTreeMap::new(),
            detail: None,
        }
    }

    pub fn with_package(mut self, name: impl Into<String>, version: impl Into<String>) -> Self {
        self.installed_packages.insert(name.into(), version.into());
        self
    }

    pub fn load(path: &Path, engine_version: impl Into<String>) -> Self {
        let engine_version = engine_version.into();
        match fs::read_to_string(path) {
            Ok(contents) => match serde_json::from_str(&contents) {
                Ok(state) => state,
                Err(error) => {
                    Self::broken(engine_version, format!("invalid runtime state: {error}"))
                }
            },
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                Self::missing(engine_version)
            }
            Err(error) => Self::broken(
                engine_version,
                format!("could not read runtime state: {error}"),
            ),
        }
    }

    pub fn save_atomic(&self, path: &Path) -> Result<(), String> {
        let parent = path
            .parent()
            .ok_or_else(|| format!("runtime state path has no parent: {}", path.display()))?;
        fs::create_dir_all(parent)
            .map_err(|error| format!("could not create {}: {error}", parent.display()))?;
        let temporary = parent.join(format!(
            ".{}.{}.tmp",
            path.file_name().unwrap_or_default().to_string_lossy(),
            std::process::id()
        ));
        let data = serde_json::to_vec_pretty(self)
            .map_err(|error| format!("could not serialize runtime state: {error}"))?;
        fs::write(&temporary, data)
            .map_err(|error| format!("could not write {}: {error}", temporary.display()))?;
        fs::rename(&temporary, path).map_err(|error| {
            let _ = fs::remove_file(&temporary);
            format!("could not replace {}: {error}", path.display())
        })
    }

    fn broken(engine_version: String, detail: String) -> Self {
        Self {
            schema_version: STATE_SCHEMA_VERSION,
            status: RuntimeStatus::Broken,
            engine_version,
            python_version: None,
            venv_path: None,
            installed_packages: BTreeMap::new(),
            detail: Some(detail),
        }
    }

    pub fn health(&self, expected_engine_version: &str) -> RuntimeHealth {
        if self.schema_version != STATE_SCHEMA_VERSION {
            return RuntimeHealth::UpgradeRequired;
        }
        if self.status == RuntimeStatus::Ready && self.engine_version != expected_engine_version {
            return RuntimeHealth::UpgradeRequired;
        }
        match self.status {
            RuntimeStatus::Ready if self.python_version.is_some() && self.venv_path.is_some() => {
                RuntimeHealth::Ready
            }
            RuntimeStatus::Ready => RuntimeHealth::Broken,
            RuntimeStatus::Missing => RuntimeHealth::Missing,
            RuntimeStatus::Installing => RuntimeHealth::Installing,
            RuntimeStatus::Broken => RuntimeHealth::Broken,
            RuntimeStatus::UpgradeRequired => RuntimeHealth::UpgradeRequired,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RuntimeHealth {
    Missing,
    Installing,
    Ready,
    Broken,
    UpgradeRequired,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommandSpec {
    pub program: PathBuf,
    pub arguments: Vec<String>,
    pub environment: BTreeMap<String, String>,
}

pub fn install_commands(
    paths: &AppPaths,
    uv_sidecar: &Path,
    engine_dir: &Path,
) -> Vec<CommandSpec> {
    let environment = BTreeMap::from([
        (
            "UV_PYTHON_INSTALL_DIR".into(),
            paths.runtime_python_dir().display().to_string(),
        ),
        (
            "UV_CACHE_DIR".into(),
            paths.app_cache().join("uv").display().to_string(),
        ),
        ("UV_PYTHON_NO_REGISTRY".into(), "1".into()),
    ]);
    vec![
        CommandSpec {
            program: uv_sidecar.to_path_buf(),
            arguments: vec![
                "python".into(),
                "install".into(),
                PYTHON_VERSION.into(),
                "--no-bin".into(),
            ],
            environment: environment.clone(),
        },
        CommandSpec {
            program: uv_sidecar.to_path_buf(),
            arguments: vec![
                "venv".into(),
                "--python".into(),
                PYTHON_VERSION.into(),
                "--managed-python".into(),
                paths.runtime_venv_dir().display().to_string(),
            ],
            environment: environment.clone(),
        },
        CommandSpec {
            program: uv_sidecar.to_path_buf(),
            arguments: vec![
                "pip".into(),
                "install".into(),
                "--python".into(),
                paths.runtime_python_executable().display().to_string(),
                "--upgrade".into(),
                engine_dir.display().to_string(),
                format!("Pillow=={PILLOW_VERSION}"),
            ],
            environment,
        },
    ]
}

pub fn ensure_runtime(
    paths: &AppPaths,
    uv_sidecar: &Path,
    engine_dir: &Path,
    engine_version: &str,
) -> Result<PathBuf, String> {
    paths.ensure_base_directories()?;
    let state_path = paths.runtime_state_path();
    let state = RuntimeState::load(&state_path, engine_version);
    let python = paths.runtime_python_executable();
    if state.health(engine_version) == RuntimeHealth::Ready && python.is_file() {
        return Ok(python);
    }

    let lock = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(paths.runtime_lock_path())
        .map_err(|error| {
            format!("runtime installation is already in progress or unavailable: {error}")
        })?;
    drop(lock);

    let result = (|| {
        RuntimeState {
            status: RuntimeStatus::Installing,
            ..RuntimeState::missing(engine_version)
        }
        .save_atomic(&state_path)?;

        for command in install_commands(paths, uv_sidecar, engine_dir) {
            run_command(&command)?;
        }
        if !python.is_file() {
            return Err(format!("runtime setup did not create {}", python.display()));
        }
        RuntimeState::ready(engine_version, PYTHON_VERSION, paths.runtime_venv_dir())
            .with_package("auvide", engine_version)
            .with_package("Pillow", PILLOW_VERSION)
            .save_atomic(&state_path)?;
        Ok(python)
    })();

    let _ = fs::remove_file(paths.runtime_lock_path());
    if let Err(error) = &result {
        RuntimeState::broken(engine_version.into(), error.clone()).save_atomic(&state_path)?;
    }
    result
}

fn run_command(spec: &CommandSpec) -> Result<(), String> {
    let output = Command::new(&spec.program)
        .args(&spec.arguments)
        .envs(&spec.environment)
        .output()
        .map_err(|error| format!("could not run {}: {error}", spec.program.display()))?;
    if output.status.success() {
        return Ok(());
    }
    Err(format!(
        "{} failed: {}",
        spec.program.display(),
        String::from_utf8_lossy(&output.stderr).trim()
    ))
}

#[cfg(test)]
mod tests {
    use super::{
        install_commands, RuntimeHealth, RuntimeState, RuntimeStatus, PILLOW_VERSION,
        PYTHON_VERSION, STATE_SCHEMA_VERSION,
    };
    use crate::paths::AppPaths;
    use std::fs;
    use std::path::PathBuf;

    fn temporary_state_path(name: &str) -> PathBuf {
        std::env::temp_dir()
            .join(format!(
                "auvide-runtime-test-{}-{}",
                std::process::id(),
                name
            ))
            .join("state.json")
    }

    #[test]
    fn missing_runtime_is_not_ready() {
        let state = RuntimeState::missing("0.2.0");

        assert_eq!(state.status, RuntimeStatus::Missing);
        assert_eq!(state.health("0.2.0"), RuntimeHealth::Missing);
    }

    #[test]
    fn ready_runtime_requires_matching_engine_and_complete_details() {
        let state = RuntimeState::ready("0.2.0", "3.12.0", PathBuf::from("runtime/venv"));

        assert_eq!(state.health("0.2.0"), RuntimeHealth::Ready);
        assert_eq!(state.health("0.3.0"), RuntimeHealth::UpgradeRequired);
    }

    #[test]
    fn unknown_schema_requires_an_upgrade() {
        let mut state = RuntimeState::missing("0.2.0");
        state.schema_version = STATE_SCHEMA_VERSION + 1;

        assert_eq!(state.health("0.2.0"), RuntimeHealth::UpgradeRequired);
    }

    #[test]
    fn incomplete_ready_record_is_broken() {
        let mut state = RuntimeState::missing("0.2.0");
        state.status = RuntimeStatus::Ready;

        assert_eq!(state.health("0.2.0"), RuntimeHealth::Broken);
    }

    #[test]
    fn persists_and_recovers_a_complete_runtime_state() {
        let path = temporary_state_path("round-trip");
        let state = RuntimeState::ready("0.2.0", "3.12.0", PathBuf::from("runtime/venv"))
            .with_package("Pillow", "11.3.0");

        state.save_atomic(&path).unwrap();
        let recovered = RuntimeState::load(&path, "0.2.0");

        assert_eq!(recovered, state);
        assert_eq!(
            recovered.installed_packages.get("Pillow"),
            Some(&"11.3.0".into())
        );
        fs::remove_dir_all(path.parent().unwrap()).unwrap();
    }

    #[test]
    fn missing_or_corrupt_state_is_recoverable() {
        let missing = temporary_state_path("missing");
        assert_eq!(
            RuntimeState::load(&missing, "0.2.0").status,
            RuntimeStatus::Missing
        );

        let corrupt = temporary_state_path("corrupt");
        fs::create_dir_all(corrupt.parent().unwrap()).unwrap();
        fs::write(&corrupt, "not json").unwrap();
        let state = RuntimeState::load(&corrupt, "0.2.0");

        assert_eq!(state.status, RuntimeStatus::Broken);
        assert!(state.detail.unwrap().contains("invalid runtime state"));
        fs::remove_dir_all(corrupt.parent().unwrap()).unwrap();
    }

    #[test]
    fn install_commands_keep_python_and_cache_under_app_owned_paths() {
        let paths = AppPaths::from_roots(PathBuf::from("app-data"), PathBuf::from("app-cache"));
        let commands = install_commands(
            &paths,
            PathBuf::from("uv").as_path(),
            PathBuf::from("engine").as_path(),
        );

        assert_eq!(commands.len(), 3);
        assert!(commands[0].arguments.contains(&PYTHON_VERSION.into()));
        assert!(commands[1].arguments.contains(&"--managed-python".into()));
        assert!(commands[2]
            .arguments
            .contains(&format!("Pillow=={PILLOW_VERSION}")));
        assert_eq!(
            commands[0].environment["UV_PYTHON_INSTALL_DIR"],
            paths.runtime_python_dir().display().to_string()
        );
        assert_eq!(
            commands[0].environment["UV_CACHE_DIR"],
            paths.app_cache().join("uv").display().to_string()
        );
        assert!(commands[2]
            .arguments
            .contains(&paths.runtime_python_executable().display().to_string()));
    }
}
