import { blockers, compareText, orderedIssues, status, statuses } from "./model.js";
import type { Epic, Issue } from "./model.js";

function cell(value: string): string {
  let result = "";
  for (const char of value) {
    if (char === "\r" || char === "\n") result += " ";
    else if (/[\p{Cc}\p{Cf}\p{Zl}\p{Zp}]/u.test(char)) {
      result += "&#92;u" + char.codePointAt(0)!.toString(16).padStart(4, "0");
    } else if ("&<>|\x60[]*_\\".includes(char)) result += "&#" + char.codePointAt(0) + ";";
    else result += char;
  }
  return result;
}

export function renderBoard(issues: Map<string, Issue>, generated: string,
  epics: Map<string, Epic> = new Map()): string {
  const groups = new Map<string | null, Issue[]>();
  for (const key of [...epics.keys()].sort(compareText)) groups.set(key, []);
  groups.set(null, []);
  for (const issue of orderedIssues(issues)) groups.get(issue.epic)!.push(issue);
  const name = (key: string | null): string => key === null ? "No epic" : cell(epics.get(key)!.title) + " (" + key + ")";
  const lines = ["# Beadcrumbs board", "", "Generated at " + generated + ".", "",
    "Snapshot of the issue store. Regenerate with --board. Manual edits are replaced.", "",
    "## Summary", "", "| Epic | Ready | Blocked | Claimed | Closed |", "| --- | --- | --- | --- | --- |"];
  for (const [key, members] of groups) {
    const counts = statuses.map(state => members.filter(issue => status(issue, issues) === state).length);
    lines.push("| " + name(key) + " | " + counts.join(" | ") + " |");
  }
  lines.push("");
  for (const [key, members] of groups) {
    lines.push("## " + name(key), "");
    if (!members.length) {
      lines.push("No issues.", "");
      continue;
    }
    lines.push("| Status | ID | Type | Priority | Title | Labels | Agent | Blockers |",
      "| --- | --- | --- | --- | --- | --- | --- | --- |");
    const rank = (issue: Issue): number => statuses.indexOf(status(issue, issues));
    for (const issue of [...members].sort((a, b) => rank(a) - rank(b))) {
      const columns = [status(issue, issues), issue.id, issue.type, "P" + issue.priority, issue.title,
        issue.labels.join(", ") || "—", issue.claim?.agent ?? "—",
        blockers(issue, issues).map(item => item.id + " (" + item.state + ")").join(", ") || "—"];
      lines.push("| " + columns.map(cell).join(" | ") + " |");
    }
    lines.push("");
  }
  return lines.join("\n");
}

export function outputJson(value: unknown, compact: boolean): string {
  return JSON.stringify(value, null, compact ? undefined : 2)
    .replace(/[\u007f-\uffff]/g, char => "\\u" + char.charCodeAt(0).toString(16).padStart(4, "0"));
}

export function safeText(value: unknown): string {
  return outputJson(String(value), true).slice(1, -1);
}
