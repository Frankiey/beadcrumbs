import assert from "node:assert/strict";
import { test } from "node:test";
import * as fs from "node:fs";
import * as path from "node:path";
import * as os from "node:os";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { decodeJson, encodeJson, JsonIssueCodec } from "../dist/codec.js";
import { validateIssue } from "../dist/model.js";
import { parseArguments } from "../dist/arguments.js";
import { runAction } from "../dist/commands.js";
import { initializeStore, loadIssues, withStoreLock } from "../dist/store.js";
import { renderBoard } from "../dist/render.js";

const cli = fileURLToPath(new URL("../dist/cli.js", import.meta.url));

test("strict JSON preserves Unicode and rejects invalid wire records", () => {
  const value = { text: "line\nλ😀", revision: 1, value: null };
  assert.deepEqual(JSON.parse(JSON.stringify(decodeJson(encodeJson(value)))), value);
  for (const source of ['{"x":1,"x":2}', '{"x":1.0}', '{"x":1e0}', '{"x":NaN}',
    '{"x":9007199254740992}', '{"x":"\\ud800"}', '{"x":1,}', '[1,]', '{"x":01}',
    '{"x":"unclosed}', '{} trailing', '\ufeff{}']) {
    assert.throws(() => decodeJson(Buffer.from(source)));
  }
  assert.throws(() => decodeJson(Buffer.from([0xff])));
  assert.throws(() => new JsonIssueCodec().filename("../escape"));
  const proto = decodeJson(Buffer.from('{"__proto__":{"safe":true}}'));
  assert.equal(Object.getPrototypeOf(proto), null);
  assert.equal(proto.__proto__.safe, true);
});

test("alternate issue codec supports lifecycle and pure rendering", () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "beadcrumbs-codec-"));
  const root = path.join(workspace, ".beadcrumbs");
  const codec = {
    accepts: name => name.endsWith(".example"),
    filename: id => id + ".example",
    encode: issue => Buffer.concat([Buffer.from("example\n"), encodeJson(issue)]),
    decode: bytes => {
      assert.equal(bytes.subarray(0, 8).toString(), "example\n");
      return decodeJson(bytes.subarray(8));
    },
  };
  try {
    withStoreLock(root, true, () => {
      initializeStore(root);
      const call = (...args) => runAction(parseArguments(args), root, loadIssues(root, codec), codec);
      const issue = call("--create", "Alternate");
      const claim = call("--claim", issue.id, "--agent", "worker");
      call("--note", issue.id, "--agent", "worker", "--text", "Done");
      const closed = call("--close", issue.id, "--token", claim.claim.token);
      assert.equal(closed.revision, 4);
      validateIssue(closed);
      const issues = loadIssues(root, codec);
      const before = JSON.stringify([...issues]);
      assert.match(renderBoard(issues, "2026-11-14T00:00:00Z"), /\| closed \| /);
      assert.equal(JSON.stringify([...issues]), before);
      assert.deepEqual(fs.readdirSync(path.join(root, "issues")), [issue.id + ".example"]);
    });
  } finally { fs.rmSync(workspace, { recursive: true }); }
});

test("process interruption before and after replacement preserves complete records", () => {
  for (const phase of ["before", "after"]) {
    const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "beadcrumbs-crash-"));
    const call = args => spawnSync(process.execPath, [cli, ...args, "--json"], { cwd: workspace, encoding: "utf8" });
    try {
      assert.equal(call(["--init"]).status, 0);
      const issue = JSON.parse(call(["--create", "Crash"]).stdout);
      const hook = 'import fs from "node:fs"; import {syncBuiltinESMExports} from "node:module"; ' +
        'const original = fs.renameSync; fs.renameSync = (source, target) => {' +
        (phase === "after" ? "original(source, target);" : "") +
        'process.exit(77); }; syncBuiltinESMExports();';
      const interrupted = spawnSync(process.execPath, [
        "--import", "data:text/javascript," + encodeURIComponent(hook), cli,
        "--claim", issue.id, "--agent", "worker", "--json",
      ], { cwd: workspace, encoding: "utf8" });
      assert.equal(interrupted.status, 77, interrupted.stderr);
      const root = path.join(workspace, ".beadcrumbs");
      const record = JSON.parse(fs.readFileSync(path.join(root, "issues", issue.id + ".json")));
      assert.equal(record.state, phase === "before" ? "open" : "claimed");
      assert.equal(record.revision, phase === "before" ? 1 : 2);
      fs.rmdirSync(path.join(root, ".writer.lock"));
      assert.equal(call(["--validate"]).status, 0);
    } finally { fs.rmSync(workspace, { recursive: true }); }
  }
});

test("failed fsync leaves the original issue and clears scratch and lock", () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "beadcrumbs-fsync-"));
  const call = args => spawnSync(process.execPath, [cli, ...args, "--json"], { cwd: workspace, encoding: "utf8" });
  try {
    assert.equal(call(["--init"]).status, 0);
    const issue = JSON.parse(call(["--create", "Failure"]).stdout);
    const root = path.join(workspace, ".beadcrumbs");
    const file = path.join(root, "issues", issue.id + ".json");
    const original = fs.readFileSync(file);
    const hook = 'import fs from "node:fs"; import {syncBuiltinESMExports} from "node:module"; ' +
      'fs.fsyncSync = () => {throw new Error("injected fsync failure");}; syncBuiltinESMExports();';
    const failed = spawnSync(process.execPath, ["--import",
      "data:text/javascript," + encodeURIComponent(hook), cli, "--claim", issue.id, "--agent", "worker", "--json",
    ], { cwd: workspace, encoding: "utf8" });
    assert.equal(failed.status, 1);
    assert.deepEqual(fs.readFileSync(file), original);
    assert.deepEqual(fs.readdirSync(path.join(root, "issues")), [issue.id + ".json"]);
    assert.equal(fs.existsSync(path.join(root, ".writer.lock")), false);
  } finally { fs.rmSync(workspace, { recursive: true }); }
});
