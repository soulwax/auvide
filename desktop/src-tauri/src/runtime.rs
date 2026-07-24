//! Serializable state transitions for the desktop-managed Python runtime.

use std::path::PathBuf;

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
            detail: None,
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
    use std::path::PathBuf;

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
}
