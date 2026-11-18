use crate::{model::*, store};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs,
    io::{Read, Write},
    path::Path,
};

const ACTIONS: &[&str] = &[
    "init",
    "create",
    "show",
    "list",
    "ready",
    "blocked",
    "validate",
    "claim",
    "note",
    "release",
    "close",
    "set-epic",
    "create-epic",
    "edit-epic",
    "show-epic",
    "epics",
    "board",
    "help",
    "version",
];
const ISSUE_ACTIONS: &[&str] = &["show", "claim", "note", "release", "close", "set-epic"];
const EPIC_ACTIONS: &[&str] = &["create-epic", "edit-epic", "show-epic"];
pub struct Arguments {
    pub action: String,
    pub value: String,
    pub options: HashMap<String, String>,
    pub dependencies: Vec<String>,
}
impl Arguments {
    pub fn get(&self, key: &str) -> &str {
        self.options.get(key).map(String::as_str).unwrap_or("")
    }
}
pub fn parse(argv: &[String]) -> Result<Arguments> {
    let mut args = Arguments {
        action: String::new(),
        value: String::new(),
        options: HashMap::new(),
        dependencies: Vec::new(),
    };
    let values = [
        "create",
        "show",
        "claim",
        "note",
        "release",
        "close",
        "set-epic",
        "create-epic",
        "edit-epic",
        "show-epic",
        "type",
        "priority",
        "epic",
        "title",
        "workspace",
        "state",
        "agent",
        "token",
        "text",
        "description",
        "description-file",
        "acceptance-criteria",
        "depends-on",
    ];
    let parsed: Result<()> = (|| {
        let mut index = 0;
        while index < argv.len() {
            let word = argv[index]
                .strip_prefix("--")
                .ok_or_else(|| Failure::new("Expected long option", 2))?;
            let (name, inline) = match word.split_once('=') {
                Some((n, v)) => (n, Some(v)),
                None => (word, None),
            };
            require(
                ACTIONS.contains(&name) || values.contains(&name) || name == "json",
                "Unknown option",
            )?;
            require(
                name == "depends-on" || !args.options.contains_key(name),
                "Repeated option",
            )?;
            let value = if values.contains(&name) {
                if let Some(value) = inline {
                    value.to_string()
                } else {
                    index += 1;
                    require(
                        index < argv.len() && !argv[index].starts_with("--"),
                        "Missing value",
                    )?;
                    argv[index].clone()
                }
            } else {
                require(inline.is_none(), "Flag takes no value")?;
                String::new()
            };
            if ACTIONS.contains(&name) {
                require(args.action.is_empty(), "One action required")?;
                args.action = name.into();
                args.value = value.clone();
            }
            if name == "depends-on" {
                args.dependencies.push(value.clone());
            }
            args.options.insert(name.into(), value);
            index += 1;
        }
        require(!args.action.is_empty(), "Action required")?;
        let specific: &[&str] = match args.action.as_str() {
            "create" => &[
                "depends-on",
                "description",
                "description-file",
                "acceptance-criteria",
                "type",
                "priority",
                "epic",
            ],
            "list" => &["state", "type", "epic"],
            "ready" => &["type", "epic"],
            "set-epic" => &["epic"],
            "create-epic" => &["title", "description", "description-file"],
            "edit-epic" => &["description", "description-file"],
            "claim" => &["agent"],
            "note" => &["agent", "text"],
            "release" | "close" => &["token"],
            _ => &[],
        };
        for key in args.options.keys() {
            let common = !["help", "version"].contains(&args.action.as_str())
                && ["workspace", "json"].contains(&key.as_str());
            require(
                key == &args.action || specific.contains(&key.as_str()) || common,
                "Option does not apply",
            )?;
        }
        let action = args.action.as_str();
        if ISSUE_ACTIONS.contains(&action) {
            require(id_valid(&args.value), "Invalid ID")?;
        }
        if EPIC_ACTIONS.contains(&action) {
            require(epic_key_valid(&args.value), "Invalid epic key")?;
        }
        if let Some(kind) = args.options.get("type") {
            require(ISSUE_TYPES.contains(&kind.as_str()), "Invalid type")?;
        }
        if let Some(priority) = args.options.get("priority") {
            require(
                priority.len() == 1 && (b'0'..=b'4').contains(&priority.as_bytes()[0]),
                "Priority must be 0 through 4",
            )?;
        }
        if action == "set-epic" {
            require(args.options.contains_key("epic"), "--epic is required")?;
        }
        if let Some(epic) = args.options.get("epic") {
            require(epic == "none" || epic_key_valid(epic), "Invalid epic key")?;
        }
        if action == "create-epic" {
            require(!args.get("title").is_empty(), "--title is required")?;
        }
        if action == "edit-epic" {
            require(
                args.options.contains_key("description")
                    || args.options.contains_key("description-file"),
                "A new description is required",
            )?;
        }
        if args.action == "create" {
            require(!args.value.is_empty(), "Empty title")?;
        }
        if ["claim", "note"].contains(&args.action.as_str()) {
            require(agent_valid(args.get("agent")), "Agent required")?;
        }
        if ["release", "close"].contains(&args.action.as_str()) {
            require(token_valid(args.get("token")), "Token required")?;
        }
        if args.action == "note" {
            require(!args.get("text").is_empty(), "Text required")?;
        }
        if args.options.contains_key("state") {
            require(
                ["open", "claimed", "closed"].contains(&args.get("state")),
                "Invalid state",
            )?;
        }
        let mut seen = std::collections::HashSet::new();
        for dep in &args.dependencies {
            require(id_valid(dep) && seen.insert(dep), "Invalid dependency")?;
        }
        require(
            !(args.options.contains_key("description")
                && args.options.contains_key("description-file")),
            "Conflicting description inputs",
        )?;
        Ok(())
    })();
    if let Err(mut error) = parsed {
        error.code = 2;
        return Err(error);
    }
    if let Some(file) = args.options.get("description-file") {
        let bytes = if file == "-" {
            let mut b = Vec::new();
            std::io::stdin().read_to_end(&mut b)?;
            b
        } else {
            fs::read(file)?
        };
        let text = String::from_utf8(bytes).map_err(|e| Failure::new(e.to_string(), 2))?;
        if text.starts_with('\u{feff}') {
            return Err(Failure::new("Description BOM is invalid", 2));
        }
        args.options.insert("description".into(), text);
    }
    Ok(args)
}
fn control(char: char) -> bool {
    let n = char as u32;
    char.is_control()
        || matches!(n,0xad|0x600..=0x605|0x61c|0x6dd|0x70f|0x890..=0x891|0x8e2|0x180e|
        0x200b..=0x200f|0x2028..=0x202e|0x2060..=0x2064|0x2066..=0x206f|0xfeff|0xfff9..=0xfffb|
        0x110bd|0x110cd|0x13430..=0x1343f|0x1bca0..=0x1bca3|0x1d173..=0x1d17a|0xe0001|0xe0020..=0xe007f)
}
fn cell(value: &str) -> String {
    let mut output = String::new();
    for c in value.chars() {
        if c == '\r' || c == '\n' {
            output.push(' ');
        } else if control(c) {
            output.push_str(&format!("&#92;u{:04x}", c as u32));
        } else if "&<>|\u{60}[]*_\\".contains(c) {
            output.push_str(&format!("&#{};", c as u32));
        } else {
            output.push(c);
        }
    }
    output
}
pub fn board(issues: &Issues, epics: &Epics, generated: &str) -> String {
    let mut keys: Vec<Option<&str>> = epics.keys().map(|k| Some(k.as_str())).collect();
    keys.push(None);
    let name = |key: Option<&str>| match key {
        Some(key) => format!("{} ({key})", cell(field(&epics[key], "title"))),
        None => "No epic".to_string(),
    };
    let members = |key: Option<&str>| -> Vec<&Issue> {
        ordered(issues)
            .into_iter()
            .filter(|issue| issue["epic"].as_str() == key)
            .collect()
    };
    let mut lines: Vec<String> = vec![
        "# Beadcrumbs board".into(),
        "".into(),
        format!("Generated at {generated}."),
        "".into(),
        "Snapshot of the issue store. Regenerate with --board. Manual edits are replaced.".into(),
        "".into(),
        "## Summary".into(),
        "".into(),
        "| Epic | Ready | Blocked | Claimed | Closed |".into(),
        "| --- | --- | --- | --- | --- |".into(),
    ];
    for key in &keys {
        let group = members(*key);
        let counts: Vec<String> = STATUSES
            .iter()
            .map(|state| {
                group
                    .iter()
                    .filter(|issue| status(issue, issues) == *state)
                    .count()
                    .to_string()
            })
            .collect();
        lines.push(format!("| {} | {} |", name(*key), counts.join(" | ")));
    }
    lines.push("".into());
    for key in &keys {
        lines.push(format!("## {}", name(*key)));
        lines.push("".into());
        let group = members(*key);
        if group.is_empty() {
            lines.push("No issues.".into());
            lines.push("".into());
            continue;
        }
        lines.push("| Status | ID | Type | Priority | Title | Agent | Blockers |".into());
        lines.push("| --- | --- | --- | --- | --- | --- | --- |".into());
        for state in STATUSES {
            for issue in group.iter().filter(|issue| status(issue, issues) == *state) {
                let owner = issue["claim"]
                    .as_object()
                    .map(|c| field(c, "agent"))
                    .unwrap_or("—");
                let deps = blockers(issue, issues)
                    .iter()
                    .map(|v| {
                        format!(
                            "{} ({})",
                            v["id"].as_str().unwrap(),
                            v["state"].as_str().unwrap()
                        )
                    })
                    .collect::<Vec<_>>()
                    .join(", ");
                let deps = if deps.is_empty() { "—" } else { &deps };
                let priority = format!("P{}", issue["priority"].as_u64().unwrap());
                let cells = [
                    *state,
                    field(issue, "id"),
                    field(issue, "type"),
                    &priority,
                    field(issue, "title"),
                    owner,
                    deps,
                ];
                let cells: Vec<String> = cells.iter().map(|c| cell(c)).collect();
                lines.push(format!("| {} |", cells.join(" | ")));
            }
        }
        lines.push("".into());
    }
    lines.join("\n")
}
fn find_epic<'a>(key: &str, epics: &'a Epics) -> Result<&'a Epic> {
    epics
        .get(key)
        .ok_or_else(|| Failure::new(format!("Epic not found: {key}"), 3))
}
fn in_scope(args: &Arguments, issue: &Issue, epics: &Epics) -> Result<bool> {
    if args.options.contains_key("type") && field(issue, "type") != args.get("type") {
        return Ok(false);
    }
    match args.options.get("epic").map(String::as_str) {
        None => Ok(true),
        Some("none") => Ok(issue["epic"].is_null()),
        Some(key) => {
            find_epic(key, epics)?;
            Ok(issue["epic"].as_str() == Some(key))
        }
    }
}
fn filtered(args: &Arguments, issues: &Issues, epics: &Epics) -> Result<Vec<Issue>> {
    let mut selected = Vec::new();
    for issue in ordered(issues) {
        let wanted = if args.action == "list" {
            !args.options.contains_key("state") || field(issue, "state") == args.get("state")
        } else {
            status(issue, issues) == "ready"
        };
        if wanted && in_scope(args, issue, epics)? {
            selected.push(issue.clone());
        }
    }
    Ok(selected)
}
pub fn run(
    args: &Arguments,
    root: &Path,
    issues: &Issues,
    epics: &Epics,
    codec: &dyn Codec,
) -> Result<Value> {
    match args.action.as_str() {
        "init" => return Ok(store::manifest()),
        "validate" => {
            return Ok(json!({"valid":true,"issue_count":issues.len(),"epic_count":epics.len()}))
        }
        "list" | "ready" => return Ok(json!(filtered(args, issues, epics)?)),
        "blocked" => {
            return Ok(json!(ordered(issues)
                .into_iter()
                .filter(|issue| status(issue, issues) == "blocked")
                .map(|issue| json!({"issue":issue,"blockers":blockers(issue,issues)}))
                .collect::<Vec<_>>()))
        }
        "epics" => return Ok(json!(epics.values().collect::<Vec<_>>())),
        "show-epic" => {
            let epic = find_epic(&args.value, epics)?;
            let members: Vec<&Issue> = ordered(issues)
                .into_iter()
                .filter(|issue| issue["epic"].as_str() == Some(args.value.as_str()))
                .collect();
            let mut counts = serde_json::Map::new();
            for state in STATUSES {
                let count = members
                    .iter()
                    .filter(|issue| status(issue, issues) == *state)
                    .count();
                counts.insert((*state).into(), json!(count));
            }
            return Ok(json!({"epic":epic,"counts":counts,"issues":members}));
        }
        "create-epic" => {
            if epics.contains_key(&args.value) {
                return Err(Failure::new("Epic already exists", 4));
            }
            store::path_kind(
                &root.join("epics").join(format!("{}.json", args.value)),
                false,
                true,
            )?;
            let created = now()?;
            let epic = json!({"key":args.value,"title":args.get("title"),"description":args.get("description"),
                "created_at":created,"updated_at":created,"revision":1})
            .as_object()
            .unwrap()
            .clone();
            store::save_epic(root, &epic)?;
            return Ok(Value::Object(epic));
        }
        "edit-epic" => {
            let mut epic = find_epic(&args.value, epics)?.clone();
            if field(&epic, "description") == args.get("description") {
                return Err(Failure::new("Epic is unchanged", 4));
            }
            let revision = epic["revision"].as_u64().unwrap();
            require(revision < MAX_REVISION, "Revision exhausted")?;
            epic.insert("description".into(), json!(args.get("description")));
            epic.insert("updated_at".into(), json!(now()?));
            epic.insert("revision".into(), json!(revision + 1));
            store::save_epic(root, &epic)?;
            return Ok(Value::Object(epic));
        }
        "board" => {
            let path = root.parent().unwrap().join("board.md");
            store::path_kind(&path, false, true)?;
            let generated = now()?;
            store::publish(&path, board(issues, epics, &generated).as_bytes())?;
            return Ok(
                json!({"path":path,"issue_count":issues.len(),"epic_count":epics.len(),"generated_at":generated}),
            );
        }
        _ => (),
    }
    let mut issue;
    if args.action == "create" {
        for dep in &args.dependencies {
            if !issues.contains_key(dep) {
                return Err(Failure::new("Issue not found", 3));
            }
        }
        let epic = match args.options.get("epic").map(String::as_str) {
            None | Some("none") => Value::Null,
            Some(key) => json!(field(find_epic(key, epics)?, "key")),
        };
        let kind = args
            .options
            .get("type")
            .map(String::as_str)
            .unwrap_or("task");
        let priority = args
            .options
            .get("priority")
            .map(|p| u64::from(p.as_bytes()[0] - b'0'))
            .unwrap_or(DEFAULT_PRIORITY);
        let mut id = format!("bc-{}", token()?);
        while issues.contains_key(&id) {
            id = format!("bc-{}", token()?);
        }
        let created = now()?;
        issue=json!({"id":id,"type":kind,"priority":priority,"epic":epic,"title":args.value,"description":args.get("description"),
            "acceptance_criteria":args.get("acceptance-criteria"),"state":"open","depends_on":args.dependencies,"claim":null,
            "notes":[],"created_at":created,"updated_at":created,"revision":1})
            .as_object().unwrap().clone();
    } else {
        issue = issues
            .get(&args.value)
            .ok_or_else(|| Failure::new("Issue not found", 3))?
            .clone();
        if args.action == "show" {
            return Ok(Value::Object(issue));
        }
        let state = field(&issue, "state");
        let mut target = Value::Null;
        if args.action == "claim" {
            if status(&issue, issues) != "ready" {
                return Err(Failure::new("Issue is not ready", 4));
            }
        } else if ["release", "close"].contains(&args.action.as_str())
            && (state != "claimed" || issue["claim"]["token"].as_str() != Some(args.get("token")))
        {
            return Err(Failure::new("Claim mismatch", 4));
        } else if args.action == "set-epic" {
            if args.get("epic") != "none" {
                target = json!(field(find_epic(args.get("epic"), epics)?, "key"));
            }
            if issue["epic"] == target {
                return Err(Failure::new("Issue epic is unchanged", 4));
            }
        }
        let revision = issue["revision"].as_u64().unwrap();
        require(revision < MAX_REVISION, "Revision exhausted")?;
        let updated = now()?;
        match args.action.as_str() {
            "claim" => {
                issue.insert("state".into(), json!("claimed"));
                issue.insert(
                    "claim".into(),
                    json!({"agent":args.get("agent"),"token":token()?}),
                );
            }
            "note" => issue
                .get_mut("notes")
                .unwrap()
                .as_array_mut()
                .unwrap()
                .push(json!({"at":updated,"by":args.get("agent"),"text":args.get("text")})),
            "release" | "close" => {
                issue.insert(
                    "state".into(),
                    json!(if args.action == "close" {
                        "closed"
                    } else {
                        "open"
                    }),
                );
                issue.insert("claim".into(), Value::Null);
            }
            "set-epic" => {
                issue.insert("epic".into(), target);
            }
            _ => return Err(Failure::new("Unsupported action", 2)),
        }
        issue.insert("revision".into(), json!(revision + 1));
        issue.insert("updated_at".into(), json!(updated));
    }
    store::save(root, &issue, codec)?;
    Ok(Value::Object(issue))
}
fn ascii_json(value: &Value, pretty: bool) -> Result<String> {
    let json = if pretty {
        serde_json::to_string_pretty(value)?
    } else {
        serde_json::to_string(value)?
    };
    let mut result = String::new();
    for char in json.chars() {
        if char as u32 > 126 {
            let mut units = [0u16; 2];
            for unit in char.encode_utf16(&mut units) {
                result.push_str(&format!("\\u{unit:04x}"));
            }
        } else {
            result.push(char);
        }
    }
    Ok(result)
}
pub fn main_entry() -> i32 {
    let result: Result<()> = (|| {
        let argv: Vec<String> = std::env::args_os()
            .skip(1)
            .map(|v| {
                v.into_string()
                    .map_err(|_| Failure::new("Invalid argument encoding", 2))
            })
            .collect::<Result<_>>()?;
        let args = parse(&argv)?;
        if args.action == "help" {
            println!(
                "Beadcrumbs offline issue tracker\n--{}",
                ACTIONS.join(" --")
            );
            return Ok(());
        }
        if args.action == "version" {
            println!("beadcrumbs 0.1.0");
            return Ok(());
        }
        let workspace = fs::canonicalize(if args.get("workspace").is_empty() {
            "."
        } else {
            args.get("workspace")
        })?;
        store::path_kind(&workspace, true, false)?;
        let root = workspace.join(".beadcrumbs");
        let codec = JsonCodec;
        let value = store::locked(&root, args.action == "init", || {
            if args.action == "init" {
                store::initialize(&root)?;
            }
            require(store::read_manifest(&root)?, "Store uninitialized")?;
            let (issues, epics) = store::load(&root, &codec)?;
            run(&args, &root, &issues, &epics, &codec)
        })?;
        writeln!(
            std::io::stdout(),
            "{}",
            ascii_json(&value, !args.options.contains_key("json"))?
        )?;
        Ok(())
    })();
    match result {
        Ok(()) => 0,
        Err(error) => {
            let message =
                ascii_json(&json!(error.message), false).unwrap_or_else(|_| "\"error\"".into());
            let _ = writeln!(std::io::stderr(), "beadcrumbs: {message}");
            error.code
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct ExampleCodec;
    impl Codec for ExampleCodec {
        fn accepts(&self, name: &str) -> bool {
            name.ends_with(".example")
        }
        fn filename(&self, id: &str) -> Result<String> {
            Ok(format!("{id}.example"))
        }
        fn encode(&self, issue: &Issue) -> Result<Vec<u8>> {
            let mut bytes = b"example\n".to_vec();
            bytes.extend(JsonCodec.encode(issue)?);
            Ok(bytes)
        }
        fn decode(&self, bytes: &[u8]) -> Result<Issue> {
            require(bytes.starts_with(b"example\n"), "Invalid example bytes")?;
            JsonCodec.decode(&bytes[8..])
        }
    }
    #[test]
    fn alternate_codec_lifecycle() {
        let folder = std::env::temp_dir().join(format!("beadcrumbs-rust-{}", token().unwrap()));
        fs::create_dir(&folder).unwrap();
        let root = folder.join(".beadcrumbs");
        let codec = ExampleCodec;
        let result = store::locked(&root, true, || {
            store::initialize(&root)?;
            let execute = |words: &[&str]| -> Result<Value> {
                let args = parse(&words.iter().map(|s| s.to_string()).collect::<Vec<_>>())?;
                let (issues, epics) = store::load(&root, &codec)?;
                run(&args, &root, &issues, &epics, &codec)
            };
            let issue = execute(&["--create", "Alternate"])?;
            let id = issue["id"].as_str().unwrap();
            let claim = execute(&["--claim", id, "--agent", "worker"])?;
            execute(&["--note", id, "--agent", "worker", "--text", "Done"])?;
            let closed = execute(&[
                "--close",
                id,
                "--token",
                claim["claim"]["token"].as_str().unwrap(),
            ])?;
            assert_eq!(closed["revision"], json!(4));
            assert_eq!(closed["state"], json!("closed"));
            assert!(root.join("issues").join(format!("{id}.example")).is_file());
            Ok(())
        });
        fs::remove_dir_all(folder).unwrap();
        result.unwrap();
    }
}
