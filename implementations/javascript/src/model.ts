export class Failure extends Error {
  code: number;
  constructor(message: string, code = 1) {
    super(message);
    this.code = code;
  }
}

export function requireValue(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Failure(message);
}

export const tokenPattern = /[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}/;
export const idPattern = /bc-[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}/;
export const agentPattern = /[A-Za-z0-9][A-Za-z0-9._-]{0,63}/;
export const maxRevision = Number.MAX_SAFE_INTEGER;
export const manifest = { format: "beadcrumbs", version: 1 } as const;

export function matches(pattern: RegExp, value: unknown): value is string {
  return typeof value === "string" && pattern.exec(value)?.[0] === value;
}

export function textValue(value: unknown, nonempty = false): asserts value is string {
  requireValue(typeof value === "string", "Expected text");
  requireValue(!nonempty || value.length > 0, "Text must be nonempty");
  requireValue(!/[\uD800-\uDFFF]/u.test(value), "Unpaired Unicode surrogate");
}

export function objectFields(value: unknown, fields: string[]): asserts value is Record<string, unknown> {
  requireValue(value !== null && typeof value === "object" && !Array.isArray(value), "Expected object");
  requireValue(Object.keys(value).length === fields.length && Object.keys(value).sort().join(",") === [...fields].sort().join(","), "Invalid object fields");
}

export function timestamp(value: unknown): asserts value is string {
  requireValue(matches(/[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z/, value),
    "Invalid timestamp");
  const time = new Date(value);
  requireValue(!value.startsWith("0000") && Number.isFinite(time.getTime()) &&
    time.toISOString().replace(".000Z", "Z") === value, "Invalid calendar timestamp");
}

export type State = "open" | "claimed" | "closed";
export interface Claim { agent: string; token: string }
export interface Note { at: string; by: string; text: string }
export interface Issue {
  id: string;
  title: string;
  description: string;
  acceptance_criteria: string;
  state: State;
  depends_on: string[];
  claim: Claim | null;
  notes: Note[];
  created_at: string;
  updated_at: string;
  revision: number;
}

export function validateIssue(value: unknown): asserts value is Issue {
  objectFields(value, ["id", "title", "description", "acceptance_criteria", "state",
    "depends_on", "claim", "notes", "created_at", "updated_at", "revision"]);
  requireValue(matches(idPattern, value.id), "Invalid issue ID");
  textValue(value.title, true);
  textValue(value.description);
  textValue(value.acceptance_criteria);
  requireValue(["open", "claimed", "closed"].includes(String(value.state)) &&
    typeof value.state === "string", "Invalid issue state");
  requireValue(Array.isArray(value.depends_on) && value.depends_on.every(dep => matches(idPattern, dep)),
    "Invalid dependencies");
  requireValue(new Set(value.depends_on).size === value.depends_on.length, "Duplicate dependency");
  if (value.state === "claimed") {
    objectFields(value.claim, ["agent", "token"]);
    requireValue(matches(agentPattern, value.claim.agent), "Invalid agent");
    requireValue(matches(tokenPattern, value.claim.token), "Invalid token");
  } else {
    requireValue(value.claim === null, "Unclaimed issue has a claim");
  }
  requireValue(Array.isArray(value.notes), "Invalid notes");
  for (const note of value.notes) {
    objectFields(note, ["at", "by", "text"]);
    timestamp(note.at);
    requireValue(matches(agentPattern, note.by), "Invalid note author");
    textValue(note.text, true);
  }
  timestamp(value.created_at);
  timestamp(value.updated_at);
  requireValue(typeof value.revision === "number" && Number.isSafeInteger(value.revision) &&
    value.revision >= 1, "Invalid revision");
}

export function validateGraph(issues: Map<string, Issue>): void {
  const counts = new Map<string, number>();
  const dependents = new Map<string, string[]>();
  for (const key of issues.keys()) dependents.set(key, []);
  for (const issue of issues.values()) {
    counts.set(issue.id, issue.depends_on.length);
    for (const id of issue.depends_on) {
      const dependency = issues.get(id);
      requireValue(dependency, "Missing dependency: " + id);
      requireValue(issue.state === "open" || dependency.state === "closed",
        "Claimed or closed issue has an unresolved dependency");
      dependents.get(id)!.push(issue.id);
    }
  }
  const queue = [...counts].filter(([, count]) => count === 0).map(([key]) => key);
  for (let index = 0; index < queue.length; index++) {
    for (const key of dependents.get(queue[index]!)!) {
      const count = counts.get(key)! - 1;
      counts.set(key, count);
      if (count === 0) queue.push(key);
    }
  }
  requireValue(queue.length === issues.size, "Dependency cycle");
}

export function blockers(issue: Issue, issues: Map<string, Issue>): {id: string; state: State}[] {
  return issue.depends_on.filter(id => issues.get(id)!.state !== "closed")
    .map(id => ({ id, state: issues.get(id)!.state }));
}

export function orderedIssues(issues: Map<string, Issue>): Issue[] {
  const compare = (a: string, b: string): number => a < b ? -1 : a > b ? 1 : 0;
  return [...issues.values()].sort((a, b) => compare(a.created_at, b.created_at) || compare(a.id, b.id));
}
