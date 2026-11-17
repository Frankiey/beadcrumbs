#!/usr/bin/env node
import * as fs from "node:fs";
import * as path from "node:path";
import { actions, parseArguments } from "./arguments.js";
import { Failure, requireValue } from "./model.js";
import { initializeStore, loadIssues, readManifest, withStoreLock } from "./store.js";
import { runAction } from "./commands.js";
import { outputJson, safeText } from "./render.js";

function main(): void {
  try {
    const args = parseArguments(process.argv.slice(2));
    if (args.action === "help") {
      fs.writeFileSync(1, "Beadcrumbs offline issue tracker\nActions: " + actions.map(name => "--" + name).join(", ") +
        "\nUse --workspace PATH and --json for store commands.\n");
      return;
    }
    if (args.action === "version") {
      fs.writeFileSync(1, "beadcrumbs 0.1.0\n");
      return;
    }
    const workspace = fs.realpathSync(args.workspace);
    requireValue(fs.statSync(workspace).isDirectory(), "Workspace must be a directory");
    const root = path.join(workspace, ".beadcrumbs");
    const result = withStoreLock(root, args.action === "init", () => {
      if (args.action === "init") initializeStore(root);
      requireValue(readManifest(root), "Store is uninitialized");
      return runAction(args, root, loadIssues(root));
    });
    fs.writeFileSync(1, outputJson(result, args.json) + "\n");
  } catch (error) {
    process.exitCode = error instanceof Failure ? error.code : 1;
    const message = error instanceof Error ? error.message : String(error);
    fs.writeFileSync(2, "beadcrumbs: " + safeText(message) + "\n");
  }
}
main();
