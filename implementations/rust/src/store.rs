use crate::model::*;
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
};

pub fn path_kind(path: &Path, directory: bool, optional: bool) -> Result<bool> {
    let metadata = match fs::symlink_metadata(path) {
        Ok(value) => value,
        Err(error) if optional && error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(error.into()),
    };
    require(!metadata.file_type().is_symlink(), "Linked protocol path")?;
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        require(
            metadata.file_attributes() & 0x400 == 0,
            "Reparse protocol path",
        )?;
    }
    require(
        if directory {
            metadata.is_dir()
        } else {
            metadata.is_file()
        },
        "Unexpected path type",
    )?;
    Ok(true)
}
fn mkdir(path: &Path) -> Result<()> {
    let mut builder = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    match builder.create(path) {
        Ok(()) => (),
        Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => (),
        Err(e) => return Err(e.into()),
    }
    path_kind(path, true, false)?;
    Ok(())
}
pub fn read_manifest(root: &Path) -> Result<bool> {
    let path = root.join("store.json");
    if !path_kind(&path, false, true)? {
        return Ok(false);
    }
    let value = decode_json(&fs::read(path)?)?;
    let object = value
        .as_object()
        .ok_or_else(|| Failure::new("Invalid manifest", 1))?;
    require(
        object.get("format") == Some(&json!("beadcrumbs"))
            && object.get("version") == Some(&json!(1)),
        "Unsupported manifest",
    )?;
    exact(object, &["format", "version"])?;
    Ok(true)
}
pub fn publish(path: &Path, bytes: &[u8]) -> Result<()> {
    let scratch = path.parent().unwrap().join(format!(".tmp-{}", token()?));
    let mut options = fs::OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options.open(&scratch)?;
    let written = (|| {
        file.write_all(bytes)?;
        file.sync_all()?;
        Ok(())
    })();
    drop(file);
    let result: Result<()> = written.and_then(|()| {
        fs::rename(&scratch, path)?;
        Ok(())
    });
    match fs::remove_file(&scratch) {
        Err(error) if error.kind() != std::io::ErrorKind::NotFound && result.is_ok() => {
            return Err(error.into())
        }
        _ => (),
    }
    result
}
pub fn locked<T>(root: &Path, initialize: bool, action: impl FnOnce() -> Result<T>) -> Result<T> {
    if initialize {
        mkdir(root)?;
    }
    path_kind(root, true, false)?;
    let exists = read_manifest(root)?;
    let lock = root.join(".writer.lock");
    if !exists && !initialize {
        if path_kind(&lock, true, true)? {
            return Err(Failure::new("Store busy", 5));
        }
        require(read_manifest(root)?, "Store uninitialized")?;
    }
    let mut builder = fs::DirBuilder::new();
    #[cfg(unix)]
    {
        use std::os::unix::fs::DirBuilderExt;
        builder.mode(0o700);
    }
    match builder.create(&lock) {
        Ok(()) => (),
        Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
            path_kind(&lock, true, false)?;
            return Err(Failure::new("Store busy", 5));
        }
        Err(error) => return Err(error.into()),
    }
    let result = action();
    fs::remove_dir(lock)?;
    result
}
pub fn initialize(root: &Path) -> Result<()> {
    if read_manifest(root)? {
        return Ok(());
    }
    for entry in fs::read_dir(root)? {
        let path = entry?.path();
        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or_else(|| Failure::new("Invalid path", 1))?;
        if name == ".writer.lock" {
            continue;
        }
        if name == "issues" {
            path_kind(&path, true, false)?;
            require(
                fs::read_dir(&path)?.next().is_none(),
                "Uninitialized issues directory is not empty",
            )?;
        } else if name.strip_prefix(".tmp-").is_some_and(token_valid) {
            path_kind(&path, false, false)?;
        } else {
            return Err(Failure::new("Unexpected uninitialized content", 1));
        }
    }
    mkdir(&root.join("issues"))?;
    publish(
        &root.join("store.json"),
        &encode_json(&json!({"format":"beadcrumbs","version":1}))?,
    )
}
pub fn load(root: &Path, codec: &dyn Codec) -> Result<Issues> {
    let directory = root.join("issues");
    path_kind(&directory, true, false)?;
    let mut paths: Vec<PathBuf> = fs::read_dir(directory)?
        .map(|e| e.map(|entry| entry.path()))
        .collect::<std::io::Result<_>>()?;
    paths.sort();
    let mut issues = Issues::new();
    for path in paths {
        let name = path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or_else(|| Failure::new("Invalid path", 1))?;
        if !codec.accepts(name) {
            continue;
        }
        path_kind(&path, false, false)?;
        let issue = codec.decode(&fs::read(&path)?)?;
        validate(&issue)?;
        let id = field(&issue, "id").to_string();
        require(name == codec.filename(&id)?, "Filename mismatch")?;
        issues.insert(id, issue);
    }
    validate_graph(&issues)?;
    Ok(issues)
}
pub fn save(root: &Path, issue: &Issue, codec: &dyn Codec) -> Result<()> {
    validate(issue)?;
    publish(
        &root
            .join("issues")
            .join(codec.filename(field(issue, "id"))?),
        &codec.encode(issue)?,
    )
}
pub fn manifest() -> Value {
    json!({"format":"beadcrumbs","version":1})
}
