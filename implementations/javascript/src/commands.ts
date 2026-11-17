import * as path from "node:path";
import { randomUUID } from "node:crypto";
import { blockers, Failure, manifest, maxRevision, orderedIssues, requireValue } from "./model.js";
import type { Issue } from "./model.js";
import { JsonIssueCodec } from "./codec.js";
import type { IssueCodec } from "./codec.js";
import type { Arguments } from "./arguments.js";
import { pathKind, publishBytes, saveIssue } from "./store.js";
import { renderBoard } from "./render.js";

function now(): string { return new Date().toISOString().replace(/\.[0-9]{3}Z$/, "Z"); }
function token(): string { return randomUUID().replaceAll("-", ""); }

export function runAction(args: Arguments, root: string, issues: Map<string, Issue>,
  codec: IssueCodec = new JsonIssueCodec()): unknown {
  const ordered = orderedIssues(issues);
  switch (args.action) {
    case "init": return manifest;
    case "validate": return { valid: true, issue_count: issues.size };
    case "list": return ordered.filter(issue => args.state === undefined || issue.state === args.state);
    case "ready": return ordered.filter(issue => issue.state === "open" && blockers(issue, issues).length === 0);
    case "blocked": return ordered.filter(issue => issue.state === "open" && blockers(issue, issues).length > 0)
      .map(issue => ({ issue, blockers: blockers(issue, issues) }));
    case "board": {
      const generated = now();
      const output = path.join(path.dirname(root), "board.md");
      pathKind(output, false, true);
      publishBytes(output, Buffer.from(renderBoard(issues, generated), "utf-8"));
      return { path: output, issue_count: issues.size, generated_at: generated };
    }
  }
  let issue: Issue;
  if (args.action === "create") {
    for (const dep of args.dependencies) {
      if (!issues.has(dep)) throw new Failure("Issue not found: " + dep, 3);
    }
    let id = "bc-" + token();
    while (issues.has(id)) id = "bc-" + token();
    const created = now();
    issue = {
      id, title: args.value, description: args.description, acceptance_criteria: args.acceptance,
      state: "open", depends_on: args.dependencies, claim: null, notes: [],
      created_at: created, updated_at: created, revision: 1,
    };
  } else {
    const current = issues.get(args.value);
    if (!current) throw new Failure("Issue not found: " + args.value, 3);
    if (args.action === "show") return current;
    issue = structuredClone(current);
    if (args.action === "claim") {
      if (issue.state !== "open" || blockers(issue, issues).length) throw new Failure("Issue is not ready", 4);
    } else if (args.action === "close" || args.action === "release") {
      if (issue.state !== "claimed" || issue.claim?.token !== args.token) throw new Failure("Claim state or token mismatch", 4);
    }
    requireValue(issue.revision < maxRevision, "Revision exhausted");
    const updated = now();
    switch (args.action) {
      case "claim": issue.state = "claimed"; issue.claim = { agent: args.agent, token: token() }; break;
      case "note": issue.notes.push({ at: updated, by: args.agent, text: args.text }); break;
      case "close": issue.state = "closed"; issue.claim = null; break;
      case "release": issue.state = "open"; issue.claim = null; break;
      default: throw new Failure("Unsupported action", 2);
    }
    issue.revision++;
    issue.updated_at = updated;
  }
  saveIssue(root, issue, codec);
  return issue;
}
