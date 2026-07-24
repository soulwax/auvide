//! Serializable state transitions for the desktop-managed Python runtime.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

pub const STATE_SCHEMA_VERSION: u32 = 1;

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

#[cfg(test)]
mod tests {
    use super::{RuntimeHealth, RuntimeState, RuntimeStatus, STATE_SCHEMA_VERSION};
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
}
