//! Typed parser for the versioned NDJSON emitted by `auvide.cli`.

use serde::{Deserialize, Serialize};

pub const PROTOCOL_NAME: &str = "auvide.progress";
pub const PROTOCOL_VERSION: u32 = 1;

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ProgressEnvelope {
    pub run_id: String,
    pub event: ProgressEvent,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum ProgressEvent {
    Plan {
        input: String,
        output: String,
        total_frames: u64,
        total_chunks: u32,
        stages: Vec<String>,
    },
    StageStarted {
        stage: String,
        ordinal: u32,
        stage_count: u32,
        chunk: Option<u32>,
    },
    Progress {
        stage: String,
        current: u64,
        total: u64,
        unit: String,
        chunk: Option<u32>,
    },
    StageCompleted {
        stage: String,
        chunk: Option<u32>,
    },
    Warning {
        code: String,
        message: String,
    },
    Completed {
        output: String,
    },
    Cancelled {
        resumable: bool,
        work_dir: String,
    },
    Failed {
        code: String,
        message: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ParsedProgressLine {
    Known(ProgressEnvelope),
    Unknown { run_id: String, event_type: String },
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProtocolError {
    InvalidJson(String),
    UnsupportedProtocol(String),
    UnsupportedVersion(u32),
    InvalidEvent(String),
}

impl std::fmt::Display for ProtocolError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidJson(error) => write!(formatter, "invalid progress JSON: {error}"),
            Self::UnsupportedProtocol(protocol) => {
                write!(formatter, "unsupported progress protocol: {protocol}")
            }
            Self::UnsupportedVersion(version) => {
                write!(
                    formatter,
                    "unsupported progress protocol version: {version}"
                )
            }
            Self::InvalidEvent(error) => write!(formatter, "invalid progress event: {error}"),
        }
    }
}

impl std::error::Error for ProtocolError {}

#[derive(Deserialize)]
struct RawEnvelope {
    protocol: String,
    version: u32,
    run_id: String,
    #[serde(rename = "type")]
    event_type: String,
}

pub fn parse_progress_line(line: &str) -> Result<ParsedProgressLine, ProtocolError> {
    let value: serde_json::Value = serde_json::from_str(line)
        .map_err(|error| ProtocolError::InvalidJson(error.to_string()))?;
    let envelope: RawEnvelope = serde_json::from_value(value.clone())
        .map_err(|error| ProtocolError::InvalidEvent(error.to_string()))?;

    if envelope.protocol != PROTOCOL_NAME {
        return Err(ProtocolError::UnsupportedProtocol(envelope.protocol));
    }
    if envelope.version != PROTOCOL_VERSION {
        return Err(ProtocolError::UnsupportedVersion(envelope.version));
    }

    if !is_known_event_type(&envelope.event_type) {
        return Ok(ParsedProgressLine::Unknown {
            run_id: envelope.run_id,
            event_type: envelope.event_type,
        });
    }

    let event = serde_json::from_value(value)
        .map_err(|error| ProtocolError::InvalidEvent(error.to_string()))?;
    Ok(ParsedProgressLine::Known(ProgressEnvelope {
        run_id: envelope.run_id,
        event,
    }))
}

fn is_known_event_type(event_type: &str) -> bool {
    matches!(
        event_type,
        "plan"
            | "stage_started"
            | "progress"
            | "stage_completed"
            | "warning"
            | "completed"
            | "cancelled"
            | "failed"
    )
}

#[cfg(test)]
mod tests {
    use super::{parse_progress_line, ParsedProgressLine, ProgressEvent, ProtocolError};

    #[test]
    fn parses_a_known_event_with_additive_fields() {
        let result = parse_progress_line(
            r#"{"protocol":"auvide.progress","version":1,"run_id":"run-1","type":"progress","stage":"encode","current":2,"total":4,"unit":"chunks","chunk":2,"future_field":true}"#,
        )
        .unwrap();

        assert_eq!(
            result,
            ParsedProgressLine::Known(super::ProgressEnvelope {
                run_id: "run-1".into(),
                event: ProgressEvent::Progress {
                    stage: "encode".into(),
                    current: 2,
                    total: 4,
                    unit: "chunks".into(),
                    chunk: Some(2),
                },
            })
        );
    }

    #[test]
    fn ignores_a_future_event_type_after_validating_the_envelope() {
        let result = parse_progress_line(
            r#"{"protocol":"auvide.progress","version":1,"run_id":"run-1","type":"future_event"}"#,
        )
        .unwrap();

        assert_eq!(
            result,
            ParsedProgressLine::Unknown {
                run_id: "run-1".into(),
                event_type: "future_event".into(),
            }
        );
    }

    #[test]
    fn rejects_malformed_or_incompatible_lines() {
        assert!(matches!(
            parse_progress_line("not json"),
            Err(ProtocolError::InvalidJson(_))
        ));
        assert!(matches!(
            parse_progress_line(
                r#"{"protocol":"other","version":1,"run_id":"run-1","type":"completed","output":"out.mp4"}"#
            ),
            Err(ProtocolError::UnsupportedProtocol(_))
        ));
        assert!(matches!(
            parse_progress_line(
                r#"{"protocol":"auvide.progress","version":2,"run_id":"run-1","type":"completed","output":"out.mp4"}"#
            ),
            Err(ProtocolError::UnsupportedVersion(2))
        ));
    }

    #[test]
    fn rejects_known_events_with_missing_required_payload() {
        assert!(matches!(
            parse_progress_line(
                r#"{"protocol":"auvide.progress","version":1,"run_id":"run-1","type":"failed","code":"pipeline_error"}"#
            ),
            Err(ProtocolError::InvalidEvent(_))
        ));
    }
}
