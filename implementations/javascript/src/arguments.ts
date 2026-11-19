import * as fs from "node:fs";
import { decodeUtf8 } from "./codec.js";
import { agentPattern, epicKey, Failure, idPattern, issueTypes, labelPattern, matches, maxLabels, requireValue,
  textValue, tokenPattern } from "./model.js";
import type { State } from "./model.js";

export const actions = ["init", "create", "show", "list", "ready", "blocked", "validate", "claim",
  "note", "release", "close", "set-epic", "relabel", "create-epic", "edit-epic", "show-epic", "epics", "board", "help",
  "version"] as const;
export type Action = typeof actions[number];
const issueActions = new Set<string>(["show", "claim", "note", "release", "close", "set-epic", "relabel"]);
const repeatable = new Set(["depends-on", "label", "add", "remove"]);
const epicActions = new Set<string>(["create-epic", "edit-epic", "show-epic"]);
const valueActions = new Set<string>(["create", ...issueActions, ...epicActions]);
const valueOptions = new Set(["workspace", "state", "agent", "token", "text", "description",
  "description-file", "acceptance-criteria", "depends-on", "type", "priority", "epic", "title", "label", "add", "remove"]);
const description = ["description", "description-file"];
const actionOptions: Partial<Record<Action, string[]>> = {
  create: ["depends-on", "acceptance-criteria", "type", "priority", "epic", "label", ...description],
  list: ["state", "type", "epic", "label"], ready: ["type", "epic", "label"], claim: ["agent"], note: ["agent", "text"],
  release: ["token"], close: ["token"], "set-epic": ["epic"], relabel: ["add", "remove"], "create-epic": ["title", ...description],
  "edit-epic": description,
};

export interface Arguments {
  action: Action;
  value: string;
  workspace: string;
  json: boolean;
  state?: State;
  agent: string;
  token: string;
  text: string;
  description: string;
  acceptance: string;
  dependencies: string[];
  type?: string;
  priority?: number;
  epic?: string;
  title: string;
  labels: string[];
  add: string[];
  remove: string[];
}

export function parseArguments(argv: string[]): Arguments {
  const options = new Map<string, string>();
  const repeated = new Map<string, string[]>([...repeatable].map(name => [name, []]));
  let action: Action | undefined;
  try {
    for (let index = 0; index < argv.length; index++) {
      const word = argv[index]!;
      requireValue(word.startsWith("--"), "Expected a long option");
      const equal = word.indexOf("=");
      const name = word.slice(2, equal < 0 ? undefined : equal);
      const isAction = (actions as readonly string[]).includes(name);
      requireValue(isAction || valueOptions.has(name) || name === "json", "Unknown option: " + name);
      requireValue(repeatable.has(name) || !options.has(name), "Repeated option: " + name);
      let value = "";
      if (valueActions.has(name) || valueOptions.has(name)) {
        if (equal >= 0) value = word.slice(equal + 1);
        else {
          const next = argv[++index];
          requireValue(next !== undefined && !next.startsWith("--"), "Missing value for " + name);
          value = next;
        }
      } else requireValue(equal < 0, "Flag does not accept a value");
      if (isAction) {
        requireValue(action === undefined, "Specify one action");
        action = name as Action;
      }
      options.set(name, value);
      repeated.get(name)?.push(value);
    }
    requireValue(action, "Specify one action");
    const dependencies = repeated.get("depends-on")!;
    const labels = repeated.get("label")!, add = repeated.get("add")!, remove = repeated.get("remove")!;
    for (const values of [labels, add, remove]) {
      requireValue(values.every(label => matches(labelPattern, label)), "Invalid label");
      requireValue(new Set(values).size === values.length, "Duplicate label");
    }
    requireValue(labels.length <= maxLabels, "Too many labels");
    if (action === "relabel") {
      requireValue(add.length || remove.length, "--add or --remove is required");
      requireValue(!add.some(label => remove.includes(label)), "A label cannot be both added and removed");
    }
    const allowed = new Set([action, ...(actionOptions[action] ?? [])]);
    if (action !== "help" && action !== "version") {
      allowed.add("workspace");
      allowed.add("json");
    }
    for (const name of options.keys()) requireValue(allowed.has(name), "Option does not apply to this action");
    const value = options.get(action)!;
    if (issueActions.has(action)) requireValue(matches(idPattern, value), "Invalid issue ID");
    if (epicActions.has(action)) requireValue(epicKey(value), "Invalid epic key");
    const type = options.get("type");
    requireValue(type === undefined || (issueTypes as readonly string[]).includes(type), "Invalid type");
    const priority = options.get("priority");
    requireValue(priority === undefined || /^[0-4]$/.test(priority), "Priority must be 0 through 4");
    const epic = options.get("epic");
    if (action === "set-epic") requireValue(epic !== undefined, "--epic is required");
    requireValue(epic === undefined || epic === "none" || epicKey(epic), "Invalid epic key");
    const title = options.get("title");
    if (action === "create-epic") textValue(title, true);
    if (action === "edit-epic") {
      requireValue(options.has("description") || options.has("description-file"), "A new description is required");
    }
    if (action === "create") textValue(value, true);
    for (const dep of dependencies) requireValue(matches(idPattern, dep), "Invalid dependency ID");
    requireValue(new Set(dependencies).size === dependencies.length, "Duplicate dependency");
    if (action === "claim" || action === "note") requireValue(matches(agentPattern, options.get("agent")), "Valid --agent is required");
    if (action === "release" || action === "close") requireValue(matches(tokenPattern, options.get("token")), "Valid --token is required");
    if (action === "note") textValue(options.get("text"), true);
    const state = options.get("state");
    requireValue(state === undefined || ["open", "claimed", "closed"].includes(state), "Invalid state");
    requireValue(!(options.has("description") && options.has("description-file")), "Conflicting description inputs");
    const description = options.get("description") ?? "";
    const acceptance = options.get("acceptance-criteria") ?? "";
    textValue(description);
    textValue(acceptance);
    const parsed: Arguments = {
      action, value, workspace: options.get("workspace") || ".", json: options.has("json"),
      state: state as State | undefined, agent: options.get("agent") ?? "",
      token: options.get("token") ?? "", text: options.get("text") ?? "",
      description, acceptance, dependencies, type, epic, title: title ?? "", labels, add, remove,
      priority: priority === undefined ? undefined : Number(priority),
    };
    // File I/O errors retain exit 1; malformed encoding is an invocation error.
    if (options.has("description-file")) {
      const file = options.get("description-file")!;
      const bytes = fs.readFileSync(file === "-" ? 0 : file);
      parsed.description = decodeUtf8(bytes);
    }
    return parsed;
  } catch (error) {
    if (error instanceof Failure) throw new Failure(error.message, 2);
    throw error;
  }
}
