import * as fs from "node:fs";
import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { decodeJson, encodeJson, JsonIssueCodec } from "./codec.js";
import type { IssueCodec } from "./codec.js";
import { Failure, manifest, matches, objectFields, requireValue, tokenPattern, validateEpic, validateGraph,
  validateIssue } from "./model.js";
import type { Epic, Issue } from "./model.js";

function isErrorCode(error: unknown, code: string): boolean {
  return error instanceof Error && "code" in error && error.code === code;
}

export function pathKind(filename: string, directory = false, optional = false): boolean {
  let info: fs.Stats;
  try {
    info = fs.lstatSync(filename);
  } catch (error) {
    if (optional && isErrorCode(error, "ENOENT")) return false;
    throw error;
  }
  requireValue(!info.isSymbolicLink(), "Linked protocol path: " + filename);
  requireValue(directory ? info.isDirectory() : info.isFile(), "Unexpected path type: " + filename);
  return true;
}

export function readManifest(root: string): boolean {
  const file = path.join(root, "store.json");
  if (!pathKind(file, false, true)) return false;
  const value = decodeJson(fs.readFileSync(file));
  requireValue(value !== null && typeof value === "object" && !Array.isArray(value), "Invalid manifest");
  const object = value as Record<string, unknown>;
  requireValue(object.format === manifest.format, "Unsupported store format");
  requireValue(object.version === manifest.version, "Unsupported store version");
  objectFields(value, ["format", "version"]);
  return true;
}

export function publishBytes(destination: string, payload: Uint8Array): void {
  const scratch = path.join(path.dirname(destination), ".tmp-" + randomUUID().replaceAll("-", ""));
  const descriptor = fs.openSync(scratch, "wx", 0o600);
  try {
    try {
      fs.writeFileSync(descriptor, payload);
      fs.fsyncSync(descriptor);
    } finally {
      fs.closeSync(descriptor);
    }
    fs.renameSync(scratch, destination);
  } finally {
    try { fs.unlinkSync(scratch); } catch (error) {
      if (!isErrorCode(error, "ENOENT")) throw error;
    }
  }
}

function createDirectory(directory: string): void {
  try { fs.mkdirSync(directory, { mode: 0o700 }); } catch (error) {
    if (!isErrorCode(error, "EEXIST")) throw error;
  }
  pathKind(directory, true);
}

export function withStoreLock<T>(root: string, initialize: boolean, operation: () => T): T {
  if (initialize) createDirectory(root);
  pathKind(root, true);
  const exists = readManifest(root);
  const lock = path.join(root, ".writer.lock");
  if (!exists && !initialize) {
    if (pathKind(lock, true, true)) throw new Failure("Store is busy", 5);
    requireValue(readManifest(root), "Store is uninitialized");
  }
  try {
    fs.mkdirSync(lock, { mode: 0o700 });
  } catch (error) {
    if (!isErrorCode(error, "EEXIST")) throw error;
    // The holder may remove the lock before we inspect it; that is still busy.
    pathKind(lock, true, true);
    throw new Failure("Store is busy", 5);
  }
  try { return operation(); } finally { fs.rmdirSync(lock); }
}

export function initializeStore(root: string): void {
  if (readManifest(root)) return;
  for (const name of fs.readdirSync(root)) {
    const file = path.join(root, name);
    if (name === ".writer.lock") continue;
    if (name === "issues" || name === "epics") {
      pathKind(file, true);
      requireValue(fs.readdirSync(file).length === 0, "Uninitialized " + name + " directory is not empty");
    } else if (name.startsWith(".tmp-") && matches(tokenPattern, name.slice(5))) {
      pathKind(file);
    } else {
      throw new Failure("Unexpected uninitialized content: " + name);
    }
  }
  createDirectory(path.join(root, "issues"));
  createDirectory(path.join(root, "epics"));
  publishBytes(path.join(root, "store.json"), encodeJson(manifest));
}

export function loadEpics(root: string): Map<string, Epic> {
  const directory = path.join(root, "epics");
  pathKind(directory, true);
  const epics = new Map<string, Epic>();
  for (const name of fs.readdirSync(directory).sort()) {
    if (!name.endsWith(".json")) continue;
    const file = path.join(directory, name);
    pathKind(file);
    const epic = decodeJson(fs.readFileSync(file));
    validateEpic(epic);
    requireValue(name === epic.key + ".json", "Epic key and filename must match");
    epics.set(epic.key, epic);
  }
  return epics;
}

export function saveEpic(root: string, epic: Epic): void {
  validateEpic(epic);
  publishBytes(path.join(root, "epics", epic.key + ".json"), encodeJson(epic));
}

export function loadIssues(root: string, codec: IssueCodec = new JsonIssueCodec(),
  epics: Map<string, Epic> = loadEpics(root)): Map<string, Issue> {
  const directory = path.join(root, "issues");
  pathKind(directory, true);
  const issues = new Map<string, Issue>();
  for (const name of fs.readdirSync(directory).sort()) {
    if (!codec.accepts(name)) continue;
    const file = path.join(directory, name);
    pathKind(file);
    const issue = codec.decode(fs.readFileSync(file));
    validateIssue(issue);
    requireValue(name === codec.filename(issue.id), "Issue ID and filename must match");
    requireValue(issue.epic === null || epics.has(issue.epic), "Missing epic: " + issue.epic);
    issues.set(issue.id, issue);
  }
  validateGraph(issues);
  return issues;
}

export function saveIssue(root: string, issue: Issue, codec: IssueCodec): void {
  validateIssue(issue);
  publishBytes(path.join(root, "issues", codec.filename(issue.id)), codec.encode(issue));
}
