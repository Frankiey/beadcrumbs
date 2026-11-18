use serde::de::{self, Deserialize, Deserializer, MapAccess, SeqAccess, Visitor};
use serde_json::{Map, Value};
use std::{
    collections::{BTreeMap, HashMap, VecDeque},
    fmt,
    time::{SystemTime, UNIX_EPOCH},
};

#[derive(Debug)]
pub struct Failure {
    pub message: String,
    pub code: i32,
}
impl Failure {
    pub fn new(message: impl Into<String>, code: i32) -> Self {
        Self {
            message: message.into(),
            code,
        }
    }
}
impl From<std::io::Error> for Failure {
    fn from(error: std::io::Error) -> Self {
        Self::new(error.to_string(), 1)
    }
}
impl From<serde_json::Error> for Failure {
    fn from(error: serde_json::Error) -> Self {
        Self::new(error.to_string(), 1)
    }
}
pub type Result<T> = std::result::Result<T, Failure>;
pub type Issue = Map<String, Value>;
pub type Issues = BTreeMap<String, Issue>;
pub type Epic = Map<String, Value>;
pub type Epics = BTreeMap<String, Epic>;
pub const MAX_REVISION: u64 = 9_007_199_254_740_991;
pub const ISSUE_TYPES: &[&str] = &["task", "bug", "chore", "docs", "spike"];
pub const STATUSES: &[&str] = &["ready", "blocked", "claimed", "closed"];
pub const DEFAULT_PRIORITY: u64 = 2;
pub fn require(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(Failure::new(message, 1))
    }
}
pub fn text(value: &Value) -> Result<&str> {
    value
        .as_str()
        .ok_or_else(|| Failure::new("Expected text", 1))
}
pub fn field<'a>(issue: &'a Issue, name: &str) -> &'a str {
    issue[name].as_str().unwrap()
}
pub fn token_valid(value: &str) -> bool {
    value.len() == 32
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        && value.as_bytes()[12] == b'4'
        && b"89ab".contains(&value.as_bytes()[16])
}
pub fn id_valid(value: &str) -> bool {
    value.strip_prefix("bc-").is_some_and(token_valid)
}
pub fn agent_valid(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value.as_bytes()[0].is_ascii_alphanumeric()
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
}
/// "none" clears an epic; the others are reserved device names on Windows.
pub fn epic_key_valid(value: &str) -> bool {
    let bytes = value.as_bytes();
    let reserved = ["none", "con", "prn", "aux", "nul"].contains(&value)
        || (bytes.len() == 4
            && (value.starts_with("com") || value.starts_with("lpt"))
            && bytes[3].is_ascii_digit());
    !value.is_empty()
        && value.len() <= 64
        && (bytes[0].is_ascii_lowercase() || bytes[0].is_ascii_digit())
        && bytes
            .iter()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || *b == b'-')
        && !reserved
}
pub fn token() -> Result<String> {
    let mut bytes = [0u8; 16];
    getrandom::fill(&mut bytes).map_err(|e| Failure::new(e.to_string(), 1))?;
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    Ok(bytes.iter().map(|b| format!("{b:02x}")).collect())
}
pub fn timestamp(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 20
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || bytes[10] != b'T'
        || bytes[13] != b':'
        || bytes[16] != b':'
        || bytes[19] != b'Z'
    {
        return false;
    }
    for (i, b) in bytes.iter().enumerate() {
        if ![4, 7, 10, 13, 16, 19].contains(&i) && !b.is_ascii_digit() {
            return false;
        }
    }
    let number = |a: usize, b: usize| value[a..b].parse::<u32>().unwrap();
    let year = number(0, 4);
    let month = number(5, 7);
    let day = number(8, 10);
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    year > 0
        && (1..=12).contains(&month)
        && day >= 1
        && day <= days[(month - 1) as usize]
        && number(11, 13) < 24
        && number(14, 16) < 60
        && number(17, 19) < 60
}
pub fn now() -> Result<String> {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| Failure::new(e.to_string(), 1))?
        .as_secs();
    // Gregorian civil date from days since Unix epoch, using 400-year eras.
    let days = (seconds / 86400) as i64 + 719468;
    let era = days / 146097;
    let day_of_era = days - era * 146097;
    let year_of_era =
        (day_of_era - day_of_era / 1460 + day_of_era / 36524 - day_of_era / 146096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_part = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_part + 2) / 5 + 1;
    let month = month_part + if month_part < 10 { 3 } else { -9 };
    if month <= 2 {
        year += 1;
    }
    require(year <= 9999, "Clock outside supported range")?;
    Ok(format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        seconds / 3600 % 24,
        seconds / 60 % 60,
        seconds % 60
    ))
}
pub fn exact(object: &Issue, fields: &[&str]) -> Result<()> {
    require(
        object.len() == fields.len() && fields.iter().all(|name| object.contains_key(*name)),
        "Invalid object fields",
    )
}
pub fn validate(issue: &Issue) -> Result<()> {
    exact(
        issue,
        &[
            "id",
            "type",
            "priority",
            "epic",
            "title",
            "description",
            "acceptance_criteria",
            "state",
            "depends_on",
            "claim",
            "notes",
            "created_at",
            "updated_at",
            "revision",
        ],
    )?;
    for name in [
        "id",
        "type",
        "title",
        "description",
        "acceptance_criteria",
        "state",
        "created_at",
        "updated_at",
    ] {
        text(&issue[name])?;
    }
    require(
        id_valid(field(issue, "id")) && !field(issue, "title").is_empty(),
        "Invalid ID or title",
    )?;
    require(ISSUE_TYPES.contains(&field(issue, "type")), "Invalid type")?;
    require(
        issue["priority"].as_u64().is_some_and(|n| n <= 4),
        "Invalid priority",
    )?;
    require(
        issue["epic"].is_null() || issue["epic"].as_str().is_some_and(epic_key_valid),
        "Invalid epic key",
    )?;
    let state = field(issue, "state");
    require(
        ["open", "claimed", "closed"].contains(&state),
        "Invalid state",
    )?;
    let dependencies = issue["depends_on"]
        .as_array()
        .ok_or_else(|| Failure::new("Invalid dependencies", 1))?;
    let mut seen = std::collections::HashSet::new();
    for dep in dependencies {
        let id = text(dep)?;
        require(id_valid(id) && seen.insert(id), "Invalid dependency")?;
    }
    if state == "claimed" {
        let claim = issue["claim"]
            .as_object()
            .ok_or_else(|| Failure::new("Missing claim", 1))?;
        exact(claim, &["agent", "token"])?;
        require(
            agent_valid(text(&claim["agent"])?) && token_valid(text(&claim["token"])?),
            "Invalid claim",
        )?;
    } else {
        require(issue["claim"].is_null(), "Unexpected claim")?;
    }
    let notes = issue["notes"]
        .as_array()
        .ok_or_else(|| Failure::new("Invalid notes", 1))?;
    for note in notes {
        let note = note
            .as_object()
            .ok_or_else(|| Failure::new("Invalid note", 1))?;
        exact(note, &["at", "by", "text"])?;
        require(
            timestamp(text(&note["at"])?)
                && agent_valid(text(&note["by"])?)
                && !text(&note["text"])?.is_empty(),
            "Invalid note",
        )?;
    }
    require(
        timestamp(field(issue, "created_at")) && timestamp(field(issue, "updated_at")),
        "Invalid timestamp",
    )?;
    require(
        issue["revision"]
            .as_u64()
            .is_some_and(|n| (1..=MAX_REVISION).contains(&n)),
        "Invalid revision",
    )
}
pub fn validate_epic(epic: &Epic) -> Result<()> {
    exact(
        epic,
        &[
            "key",
            "title",
            "description",
            "created_at",
            "updated_at",
            "revision",
        ],
    )?;
    for name in ["key", "title", "description", "created_at", "updated_at"] {
        text(&epic[name])?;
    }
    require(
        epic_key_valid(field(epic, "key")) && !field(epic, "title").is_empty(),
        "Invalid epic key or title",
    )?;
    require(
        timestamp(field(epic, "created_at")) && timestamp(field(epic, "updated_at")),
        "Invalid timestamp",
    )?;
    require(
        epic["revision"]
            .as_u64()
            .is_some_and(|n| (1..=MAX_REVISION).contains(&n)),
        "Invalid revision",
    )
}
pub fn dependencies(issue: &Issue) -> Vec<&str> {
    issue["depends_on"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap())
        .collect()
}
pub fn blockers(issue: &Issue, issues: &Issues) -> Vec<Value> {
    dependencies(issue)
        .into_iter()
        .filter(|id| field(&issues[*id], "state") != "closed")
        .map(|id| serde_json::json!({"id":id,"state":field(&issues[id],"state")}))
        .collect()
}
pub fn ordered(issues: &Issues) -> Vec<&Issue> {
    let mut rows: Vec<_> = issues.values().collect();
    rows.sort_by_key(|issue| {
        (
            issue["priority"].as_u64().unwrap(),
            field(issue, "created_at"),
            field(issue, "id"),
        )
    });
    rows
}
pub fn status(issue: &Issue, issues: &Issues) -> &'static str {
    match field(issue, "state") {
        "open" if blockers(issue, issues).is_empty() => "ready",
        "open" => "blocked",
        "claimed" => "claimed",
        _ => "closed",
    }
}
pub fn validate_graph(issues: &Issues) -> Result<()> {
    let mut counts = HashMap::new();
    let mut dependents: HashMap<&str, Vec<&str>> = HashMap::new();
    let mut queue = VecDeque::new();
    for (id, issue) in issues {
        let deps = dependencies(issue);
        counts.insert(id.as_str(), deps.len());
        if deps.is_empty() {
            queue.push_back(id.as_str());
        }
        for dep in deps {
            let target = issues
                .get(dep)
                .ok_or_else(|| Failure::new("Missing dependency", 1))?;
            require(
                field(issue, "state") == "open" || field(target, "state") == "closed",
                "Unresolved dependency on active issue",
            )?;
            dependents.entry(dep).or_default().push(id);
        }
    }
    let mut visited = 0;
    while let Some(id) = queue.pop_front() {
        visited += 1;
        if let Some(children) = dependents.get(id) {
            for child in children {
                let count = counts.get_mut(child).unwrap();
                *count -= 1;
                if *count == 0 {
                    queue.push_back(child);
                }
            }
        }
    }
    require(visited == issues.len(), "Dependency cycle")
}

// Custom deserialization rejects duplicate keys before they enter a map.
struct Strict(Value);
impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> std::result::Result<Self, D::Error> {
        struct StrictVisitor;
        impl<'de> Visitor<'de> for StrictVisitor {
            type Value = Strict;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                write!(f, "strict protocol JSON")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Strict, E> {
                Ok(Strict(v.into()))
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Strict, E> {
                Ok(Strict(Value::Null))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> std::result::Result<Strict, E> {
                Ok(Strict(v.into()))
            }
            fn visit_string<E: de::Error>(self, v: String) -> std::result::Result<Strict, E> {
                Ok(Strict(v.into()))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Strict, E> {
                if v.unsigned_abs() > MAX_REVISION {
                    return Err(E::custom("integer out of range"));
                }
                Ok(Strict(v.into()))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Strict, E> {
                if v > MAX_REVISION {
                    return Err(E::custom("integer out of range"));
                }
                Ok(Strict(v.into()))
            }
            fn visit_f64<E: de::Error>(self, _: f64) -> std::result::Result<Strict, E> {
                Err(E::custom("integer lexical form required"))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut seq: A,
            ) -> std::result::Result<Strict, A::Error> {
                let mut values = Vec::new();
                while let Some(Strict(value)) = seq.next_element()? {
                    values.push(value);
                }
                Ok(Strict(values.into()))
            }
            fn visit_map<A: MapAccess<'de>>(
                self,
                mut map: A,
            ) -> std::result::Result<Strict, A::Error> {
                let mut values = Map::new();
                while let Some(key) = map.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(de::Error::custom("duplicate JSON key"));
                    }
                    let Strict(value) = map.next_value()?;
                    values.insert(key, value);
                }
                Ok(Strict(values.into()))
            }
        }
        deserializer.deserialize_any(StrictVisitor)
    }
}
pub fn decode_json(bytes: &[u8]) -> Result<Value> {
    let Strict(value) = serde_json::from_slice(bytes)?;
    Ok(value)
}
pub fn encode_json(value: &Value) -> Result<Vec<u8>> {
    let mut data = serde_json::to_vec_pretty(value)?;
    data.push(b'\n');
    Ok(data)
}
pub trait Codec {
    fn accepts(&self, name: &str) -> bool;
    fn filename(&self, id: &str) -> Result<String>;
    fn decode(&self, bytes: &[u8]) -> Result<Issue>;
    fn encode(&self, issue: &Issue) -> Result<Vec<u8>>;
}
pub struct JsonCodec;
impl Codec for JsonCodec {
    fn accepts(&self, name: &str) -> bool {
        name.ends_with(".json")
    }
    fn filename(&self, id: &str) -> Result<String> {
        require(id_valid(id), "Invalid ID")?;
        Ok(format!("{id}.json"))
    }
    fn decode(&self, bytes: &[u8]) -> Result<Issue> {
        decode_json(bytes)?
            .as_object()
            .cloned()
            .ok_or_else(|| Failure::new("Expected issue object", 1))
    }
    fn encode(&self, issue: &Issue) -> Result<Vec<u8>> {
        encode_json(&Value::Object(issue.clone()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn strict_json_and_calendar() {
        for value in [
            r#"{"x":1,"x":2}"#,
            r#"{"x":1.0}"#,
            r#"{"x":1e0}"#,
            r#"{"x":"\ud800"}"#,
            r#"{"x":9007199254740992}"#,
        ] {
            assert!(decode_json(value.as_bytes()).is_err(), "{value}");
        }
        assert!(decode_json(br#"{"x":"\ud83d\ude00"}"#).is_ok());
        assert!(timestamp("2024-02-29T23:59:59Z"));
        assert!(!timestamp("2026-02-29T00:00:00Z"));
        assert!(timestamp(&now().unwrap()));
        assert!(token_valid(&token().unwrap()));
    }
}
