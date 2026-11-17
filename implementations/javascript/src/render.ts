import { blockers, orderedIssues } from "./model.js";
import type { Issue } from "./model.js";

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

export function renderBoard(issues: Map<string, Issue>, generated: string): string {
  const sections = new Map<string, string[]>([["Ready", []], ["Blocked", []], ["Claimed", []], ["Closed", []]]);
  for (const issue of orderedIssues(issues)) {
    const unresolved = blockers(issue, issues);
    let section = issue.state === "claimed" ? "Claimed" : "Closed";
    if (issue.state === "open") section = unresolved.length ? "Blocked" : "Ready";
    const columns = [issue.id, issue.title, issue.claim?.agent ?? "—",
      unresolved.map(item => item.id + " (" + item.state + ")").join(", ") || "—"];
    sections.get(section)!.push("| " + columns.map(cell).join(" | ") + " |");
  }
  const lines = ["# Beadcrumbs board", "", "Generated at " + generated + ".", "",
    "Snapshot of the issue store. Regenerate with --board. Manual edits are replaced.", ""];
  for (const [name, rows] of sections) {
    lines.push("## " + name + " (" + rows.length + ")", "");
    if (rows.length) lines.push("| ID | Title | Agent | Blockers |", "| --- | --- | --- | --- |", ...rows, "");
    else lines.push("No issues.", "");
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
