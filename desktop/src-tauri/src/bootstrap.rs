//! Validated bootstrap manifest model for desktop-managed dependencies.

use std::collections::BTreeMap;

use serde::Deserialize;

pub const MANIFEST_SCHEMA_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct BootstrapManifest {
    pub schema_version: u32,
    pub runtime: RuntimeRequirements,
    pub targets: BTreeMap<String, TargetArtifacts>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct RuntimeRequirements {
    pub python: String,
    pub engine: String,
    pub pillow: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct TargetArtifacts {
    pub uv: ExecutableArtifact,
    pub ffmpeg: FfmpegArtifact,
    pub realesrgan: RealesrganArtifact,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ExecutableArtifact {
    #[serde(flatten)]
    pub archive: ArchiveArtifact,
    pub executable: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct FfmpegArtifact {
    #[serde(flatten)]
    pub archive: ArchiveArtifact,
    pub ffmpeg: String,
    pub ffprobe: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct RealesrganArtifact {
    #[serde(flatten)]
    pub archive: ArchiveArtifact,
    pub executable: String,
    pub models: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ArchiveArtifact {
    pub url: String,
    pub sha256: String,
    pub archive: ArchiveFormat,
    pub license: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ArchiveFormat {
    Zip,
    TarGz,
}

impl BootstrapManifest {
    pub fn bundled() -> Result<Self, String> {
        Self::parse(include_str!("../resources/bootstrap-manifest.json"))
    }

    pub fn parse(contents: &str) -> Result<Self, String> {
        let manifest: Self = serde_json::from_str(contents)
            .map_err(|error| format!("invalid bootstrap manifest JSON: {error}"))?;
        manifest.validate()?;
        Ok(manifest)
    }

    pub fn target(&self, triple: &str) -> Result<&TargetArtifacts, String> {
        self.targets
            .get(triple)
            .ok_or_else(|| format!("bootstrap manifest does not support target {triple}"))
    }

    fn validate(&self) -> Result<(), String> {
        if self.schema_version != MANIFEST_SCHEMA_VERSION {
            return Err(format!(
                "unsupported bootstrap manifest schema version: {}",
                self.schema_version
            ));
        }
        for (name, value) in [
            ("runtime.python", &self.runtime.python),
            ("runtime.engine", &self.runtime.engine),
            ("runtime.pillow", &self.runtime.pillow),
        ] {
            if value.trim().is_empty() {
                return Err(format!("bootstrap manifest {name} must not be empty"));
            }
        }
        if self.targets.is_empty() {
            return Err("bootstrap manifest must define at least one target".into());
        }
        for (triple, target) in &self.targets {
            if triple.trim().is_empty() {
                return Err("bootstrap manifest target triple must not be empty".into());
            }
            validate_executable("uv", &target.uv)?;
            validate_archive("ffmpeg", &target.ffmpeg.archive)?;
            validate_relative_path("ffmpeg.ffmpeg", &target.ffmpeg.ffmpeg)?;
            validate_relative_path("ffmpeg.ffprobe", &target.ffmpeg.ffprobe)?;
            if target.ffmpeg.ffmpeg == target.ffmpeg.ffprobe {
                return Err("ffmpeg and ffprobe paths must be distinct".into());
            }
            validate_archive("realesrgan", &target.realesrgan.archive)?;
            validate_relative_path("realesrgan.executable", &target.realesrgan.executable)?;
            if target.realesrgan.models.is_empty() {
                return Err("realesrgan must declare at least one model path".into());
            }
            for model in &target.realesrgan.models {
                validate_relative_path("realesrgan.models", model)?;
            }
        }
        Ok(())
    }
}

fn validate_executable(name: &str, artifact: &ExecutableArtifact) -> Result<(), String> {
    validate_archive(name, &artifact.archive)?;
    validate_relative_path(&format!("{name}.executable"), &artifact.executable)
}

fn validate_archive(name: &str, artifact: &ArchiveArtifact) -> Result<(), String> {
    if !artifact.url.starts_with("https://") {
        return Err(format!("{name}.url must use HTTPS"));
    }
    if artifact.sha256.len() != 64
        || !artifact
            .sha256
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(format!(
            "{name}.sha256 must be a 64-character hexadecimal SHA256"
        ));
    }
    if artifact.license.trim().is_empty() {
        return Err(format!("{name}.license must not be empty"));
    }
    Ok(())
}

fn validate_relative_path(name: &str, value: &str) -> Result<(), String> {
    let path = std::path::Path::new(value);
    if value.trim().is_empty()
        || path.is_absolute()
        || value.contains("..")
        || value.contains('\\')
        || value.contains(':')
    {
        return Err(format!("{name} must be a safe archive-relative path"));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{BootstrapManifest, MANIFEST_SCHEMA_VERSION};

    const MANIFEST: &str = r#"{
      "schema_version": 1,
      "runtime": { "python": "3.12", "engine": "0.2.0", "pillow": "11.3.0" },
      "targets": {
        "x86_64-pc-windows-msvc": {
          "uv": { "url": "https://example.invalid/uv.zip", "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "archive": "zip", "executable": "uv.exe", "license": "MIT OR Apache-2.0" },
          "ffmpeg": { "url": "https://example.invalid/ffmpeg.zip", "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "archive": "zip", "ffmpeg": "bin/ffmpeg.exe", "ffprobe": "bin/ffprobe.exe", "license": "GPL-3.0-or-later" },
          "realesrgan": { "url": "https://example.invalid/realesrgan.zip", "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "archive": "zip", "executable": "realesrgan-ncnn-vulkan.exe", "models": ["models/realesr-animevideov3-x2.param", "models/realesr-animevideov3-x2.bin"], "license": "BSD-3-Clause" }
        }
      }
    }"#;

    #[test]
    fn parses_and_selects_a_supported_target() {
        let manifest = BootstrapManifest::parse(MANIFEST).unwrap();

        assert_eq!(manifest.schema_version, MANIFEST_SCHEMA_VERSION);
        assert_eq!(
            manifest
                .target("x86_64-pc-windows-msvc")
                .unwrap()
                .uv
                .executable,
            "uv.exe"
        );
    }

    #[test]
    fn rejects_unsafe_or_incomplete_artifact_data() {
        assert!(BootstrapManifest::parse(&MANIFEST.replace(
            "https://example.invalid/uv.zip",
            "http://example.invalid/uv.zip"
        ))
        .is_err());
        assert!(
            BootstrapManifest::parse(&MANIFEST.replace("bin/ffprobe.exe", "../ffprobe.exe"))
                .is_err()
        );
        assert!(BootstrapManifest::parse(
            &MANIFEST.replace("\"models/realesr-animevideov3-x2.bin\"", "")
        )
        .is_err());
    }

    #[test]
    fn rejects_unknown_schema_and_target() {
        let manifest = BootstrapManifest::parse(
            &MANIFEST.replace("\"schema_version\": 1", "\"schema_version\": 2"),
        );
        assert!(manifest.is_err());

        let manifest = BootstrapManifest::parse(MANIFEST).unwrap();
        assert!(manifest.target("aarch64-pc-windows-msvc").is_err());
    }

    #[test]
    fn bundled_manifest_is_valid_for_the_advertised_windows_target() {
        let manifest = BootstrapManifest::bundled().unwrap();

        assert!(manifest.target("x86_64-pc-windows-msvc").is_ok());
    }
}
