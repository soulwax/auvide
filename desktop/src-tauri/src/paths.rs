//! Platform-owned locations for auvide runtime state and downloaded tools.

use std::fs;
use std::path::{Path, PathBuf};

use tauri::{AppHandle, Manager};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AppPaths {
    app_data: PathBuf,
    app_cache: PathBuf,
}

impl AppPaths {
    pub fn from_app(app: &AppHandle) -> Result<Self, String> {
        let app_data = app
            .path()
            .app_data_dir()
            .map_err(|error| format!("could not resolve app data directory: {error}"))?;
        let app_cache = app
            .path()
            .app_cache_dir()
            .map_err(|error| format!("could not resolve app cache directory: {error}"))?;
        Ok(Self::from_roots(app_data, app_cache))
    }

    pub fn from_roots(app_data: PathBuf, app_cache: PathBuf) -> Self {
        Self {
            app_data,
            app_cache,
        }
    }

    pub fn app_data(&self) -> &Path {
        &self.app_data
    }

    pub fn app_cache(&self) -> &Path {
        &self.app_cache
    }

    pub fn runtime_dir(&self) -> PathBuf {
        self.app_data.join("runtime")
    }

    pub fn runtime_state_path(&self) -> PathBuf {
        self.runtime_dir().join("state.json")
    }

    pub fn tools_dir(&self) -> PathBuf {
        self.app_data.join("tools")
    }

    pub fn models_dir(&self) -> PathBuf {
        self.app_data.join("models")
    }

    pub fn jobs_dir(&self) -> PathBuf {
        self.app_data.join("jobs")
    }

    pub fn logs_dir(&self) -> PathBuf {
        self.app_data.join("logs")
    }

    pub fn downloads_dir(&self) -> PathBuf {
        self.app_cache.join("downloads")
    }

    pub fn ensure_base_directories(&self) -> Result<(), String> {
        let directories = [
            self.app_data.clone(),
            self.app_cache.clone(),
            self.runtime_dir(),
            self.tools_dir(),
            self.models_dir(),
            self.jobs_dir(),
            self.logs_dir(),
            self.downloads_dir(),
        ];
        for path in directories {
            fs::create_dir_all(&path)
                .map_err(|error| format!("could not create {}: {error}", path.display()))?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::AppPaths;
    use std::path::PathBuf;

    #[test]
    fn derived_paths_stay_under_the_supplied_platform_roots() {
        let paths = AppPaths::from_roots(PathBuf::from("app-data"), PathBuf::from("app-cache"));

        assert_eq!(paths.runtime_dir(), PathBuf::from("app-data/runtime"));
        assert_eq!(
            paths.runtime_state_path(),
            PathBuf::from("app-data/runtime/state.json")
        );
        assert_eq!(paths.tools_dir(), PathBuf::from("app-data/tools"));
        assert_eq!(paths.models_dir(), PathBuf::from("app-data/models"));
        assert_eq!(paths.jobs_dir(), PathBuf::from("app-data/jobs"));
        assert_eq!(paths.logs_dir(), PathBuf::from("app-data/logs"));
        assert_eq!(paths.downloads_dir(), PathBuf::from("app-cache/downloads"));
    }
}
