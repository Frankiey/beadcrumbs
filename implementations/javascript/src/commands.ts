import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { blockers, compareText, defaultPriority, Failure, manifest, maxLabels, maxRevision, orderedIssues, requireValue,
  status, statuses } from "./model.js";
import type { Epic, Issue } from "./model.js";
import { JsonIssueCodec } from "./codec.js";
import type { IssueCodec } from "./codec.js";
import type { Arguments } from "./arguments.js";
import { loadEpics, pathKind, publishBytes, saveEpic, saveIssue } from "./store.js";
import { renderBoard } from "./render.js";

function now(): string { return new Date().toISOString().replace(/\.[0-9]{3}Z$/, "Z"); }
function token(): string { return randomUUID().replaceAll("-", ""); }

function findEpic(key: string, epics: Map<string, Epic>): Epic {
  const epic = epics.get(key);
  if (!epic) throw new Failure("Epic not found: " + key, 3);
  return epic;
}

function inScope(args: Arguments, issue: Issue, epics: Map<string, Epic>): boolean {
  if (args.type !== undefined && issue.type !== args.type) return false;
  if (!args.labels.every(label => issue.labels.includes(label))) return false;
  if (args.epic === undefined) return true;
  if (args.epic === "none") return issue.epic === null;
  findEpic(args.epic, epics);
  return issue.epic === args.epic;
}

export function runAction(args: Arguments, root: string, issues: Map<string, Issue>,
  codec: IssueCodec = new JsonIssueCodec(), epics: Map<string, Epic> = loadEpics(root)): unknown {
  const ordered = orderedIssues(issues);
  switch (args.action) {
    case "init": return manifest;
    case "validate": return { valid: true, issue_count: issues.size, epic_count: epics.size };
    case "list": return ordered.filter(issue => (args.state === undefined || issue.state === args.state) &&
      inScope(args, issue, epics));
    case "ready": return ordered.filter(issue => status(issue, issues) === "ready" && inScope(args, issue, epics));
    case "blocked": return ordered.filter(issue => status(issue, issues) === "blocked")
      .map(issue => ({ issue, blockers: blockers(issue, issues) }));
    case "epics": return [...epics.keys()].sort(compareText).map(key => epics.get(key)!);
    case "show-epic": {
      const epic = findEpic(args.value, epics);
      const members = ordered.filter(issue => issue.epic === epic.key);
      const counts = Object.fromEntries(statuses.map(name =>
        [name, members.filter(issue => status(issue, issues) === name).length]));
      return { epic, counts, issues: members };
    }
    case "create-epic": {
      if (epics.has(args.value)) throw new Failure("Epic already exists: " + args.value, 4);
      pathKind(path.join(root, "epics", args.value + ".json"), false, true);
      const created = now();
      const epic: Epic = { key: args.value, title: args.title, description: args.description,
        created_at: created, updated_at: created, revision: 1 };
      saveEpic(root, epic);
      return epic;
    }
    case "edit-epic": {
      const epic = structuredClone(findEpic(args.value, epics));
      if (epic.description === args.description) throw new Failure("Epic is unchanged", 4);
      requireValue(epic.revision < maxRevision, "Revision exhausted");
      epic.description = args.description;
      epic.updated_at = now();
      epic.revision++;
      saveEpic(root, epic);
      return epic;
    }
    case "board": {
      const generated = now();
      const output = path.join(path.dirname(root), "board.md");
      pathKind(output, false, true);
      publishBytes(output, Buffer.from(renderBoard(issues, generated, epics), "utf-8"));
      return { path: output, issue_count: issues.size, epic_count: epics.size, generated_at: generated };
    }
  }
  let issue: Issue;
  if (args.action === "create") {
    for (const dep of args.dependencies) {
      if (!issues.has(dep)) throw new Failure("Issue not found: " + dep, 3);
    }
    const epic = args.epic === undefined || args.epic === "none" ? null : findEpic(args.epic, epics).key;
    let id = "bc-" + token();
    while (issues.has(id)) id = "bc-" + token();
    const created = now();
    issue = {
      id, type: args.type ?? "task", priority: args.priority ?? defaultPriority, epic,
      labels: [...args.labels].sort(compareText),
      title: args.value, description: args.description, acceptance_criteria: args.acceptance,
      state: "open", depends_on: args.dependencies, claim: null, notes: [],
      created_at: created, updated_at: created, revision: 1,
    };
  } else {
    const current = issues.get(args.value);
    if (!current) throw new Failure("Issue not found: " + args.value, 3);
    if (args.action === "show") return current;
    issue = structuredClone(current);
    let target: string | null = null;
    let labels: string[] = [];
    if (args.action === "claim") {
      if (status(issue, issues) !== "ready") throw new Failure("Issue is not ready", 4);
    } else if (args.action === "close" || args.action === "release") {
      if (issue.state !== "claimed" || issue.claim?.token !== args.token) throw new Failure("Claim state or token mismatch", 4);
    } else if (args.action === "set-epic") {
      target = args.epic === "none" ? null : findEpic(args.epic!, epics).key;
      if (issue.epic === target) throw new Failure("Issue epic is unchanged", 4);
    } else if (args.action === "relabel") {
      labels = [...new Set([...issue.labels, ...args.add])].filter(label => !args.remove.includes(label))
        .sort(compareText);
      if (labels.join(",") === issue.labels.join(",")) throw new Failure("Issue labels are unchanged", 4);
      if (labels.length > maxLabels) throw new Failure("An issue can have at most " + maxLabels + " labels", 4);
    }
    requireValue(issue.revision < maxRevision, "Revision exhausted");
    const updated = now();
    switch (args.action) {
      case "claim": issue.state = "claimed"; issue.claim = { agent: args.agent, token: token() }; break;
      case "note": issue.notes.push({ at: updated, by: args.agent, text: args.text }); break;
      case "close": issue.state = "closed"; issue.claim = null; break;
      case "release": issue.state = "open"; issue.claim = null; break;
      case "set-epic": issue.epic = target; break;
      case "relabel": issue.labels = labels; break;
      default: throw new Failure("Unsupported action", 2);
    }
    issue.revision++;
    issue.updated_at = updated;
  }
  saveIssue(root, issue, codec);
  return issue;
}
