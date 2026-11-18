using System.Globalization;
using System.Text;
using System.Text.Json.Nodes;

namespace Beadcrumbs;

public sealed class Arguments
{
    public string Action { get; private set; } = "";
    public string Value { get; private set; } = "";
    public Dictionary<string, string> Options { get; } = new(StringComparer.Ordinal);
    public List<string> Dependencies { get; } = [];
    public string Get(string key) => Options.GetValueOrDefault(key, "");
    public static readonly string[] Actions = ["init", "create", "show", "list", "ready", "blocked", "validate",
        "claim", "note", "release", "close", "set-epic", "create-epic", "edit-epic", "show-epic", "epics", "board",
        "help", "version"];
    private static readonly string[] IssueActions = ["show", "claim", "note", "release", "close", "set-epic"];
    private static readonly string[] EpicActions = ["create-epic", "edit-epic", "show-epic"];
    public static Arguments Parse(string[] argv)
    {
        var result = new Arguments();
        string[] values = ["create", .. IssueActions, .. EpicActions, "workspace", "state", "agent", "token", "text",
            "description", "description-file", "acceptance-criteria", "depends-on", "type", "priority", "epic", "title"];
        try
        {
            for (int index = 0; index < argv.Length; index++)
            {
                string word = argv[index];
                Model.Require(word.StartsWith("--", StringComparison.Ordinal), "Expected long option");
                string[] pair = word[2..].Split('=', 2);
                string name = pair[0], value = "";
                Model.Require(Actions.Contains(name) || values.Contains(name) || name == "json", "Unknown option");
                Model.Require(name == "depends-on" || !result.Options.ContainsKey(name), "Repeated option");
                if (values.Contains(name))
                {
                    if (pair.Length == 2) value = pair[1];
                    else
                    {
                        index++;
                        Model.Require(index < argv.Length && !argv[index].StartsWith("--", StringComparison.Ordinal), "Missing value");
                        value = argv[index];
                    }
                }
                else Model.Require(pair.Length == 1, "Flag takes no value");
                if (Actions.Contains(name))
                {
                    Model.Require(result.Action == "", "One action required");
                    result.Action = name; result.Value = value;
                }
                result.Options[name] = value;
                if (name == "depends-on") result.Dependencies.Add(value);
            }
            Model.Require(result.Action != "", "Action required");
            string[] specific = result.Action switch
            {
                "create" => ["depends-on", "description", "description-file", "acceptance-criteria", "type", "priority", "epic"],
                "list" => ["state", "type", "epic"],
                "ready" => ["type", "epic"],
                "set-epic" => ["epic"],
                "create-epic" => ["title", "description", "description-file"],
                "edit-epic" => ["description", "description-file"],
                "claim" => ["agent"],
                "note" => ["agent", "text"],
                "release" or "close" => ["token"],
                _ => []
            };
            foreach (string key in result.Options.Keys)
            {
                bool common = result.Action is not ("help" or "version") && key is "workspace" or "json";
                Model.Require(key == result.Action || specific.Contains(key) || common, "Option does not apply");
            }
            if (IssueActions.Contains(result.Action))
                Model.Require(Model.Matches(Model.IdPattern, result.Value), "Invalid ID");
            if (EpicActions.Contains(result.Action))
                Model.Require(Model.Matches(Model.EpicPattern, result.Value), "Invalid epic key");
            if (result.Options.TryGetValue("type", out var type)) Model.Require(Model.IssueTypes.Contains(type), "Invalid type");
            if (result.Options.TryGetValue("priority", out var priority))
                Model.Require(priority is "0" or "1" or "2" or "3" or "4", "Priority must be 0 through 4");
            if (result.Action == "set-epic") Model.Require(result.Options.ContainsKey("epic"), "--epic is required");
            if (result.Options.TryGetValue("epic", out var epic))
                Model.Require(epic == "none" || Model.Matches(Model.EpicPattern, epic), "Invalid epic key");
            if (result.Action == "create-epic") Model.Require(result.Get("title").Length > 0, "--title is required");
            if (result.Action == "edit-epic")
                Model.Require(result.Options.ContainsKey("description") || result.Options.ContainsKey("description-file"),
                    "A new description is required");
            if (result.Action == "create") Model.Require(result.Value.Length > 0, "Empty title");
            if (result.Action is "claim" or "note") Model.Require(Model.Matches(Model.AgentPattern, result.Get("agent")), "Agent required");
            if (result.Action is "release" or "close") Model.Require(Model.Matches(Model.TokenPattern, result.Get("token")), "Token required");
            if (result.Action == "note") Model.Require(result.Get("text").Length > 0, "Note text required");
            if (result.Options.ContainsKey("state")) Model.Require(result.Get("state") is "open" or "claimed" or "closed", "Invalid state");
            Model.Require(result.Dependencies.All(id => Model.Matches(Model.IdPattern, id)) &&
                result.Dependencies.Distinct().Count() == result.Dependencies.Count, "Invalid dependency");
            Model.Require(!(result.Options.ContainsKey("description") && result.Options.ContainsKey("description-file")), "Conflicting description inputs");
            foreach (string text in result.Options.Values) Model.Scalar(text);
        }
        catch (Failure error) { throw new Failure(error.Message, 2); }
        if (result.Options.TryGetValue("description-file", out var file))
        {
            byte[] bytes;
            if (file == "-")
            {
                using var memory = new MemoryStream();
                Console.OpenStandardInput().CopyTo(memory);
                bytes = memory.ToArray();
            }
            else bytes = File.ReadAllBytes(file);
            try { result.Options["description"] = JsonWire.DecodeUtf8(bytes); }
            catch (Exception error) when (error is Failure or DecoderFallbackException) { throw new Failure(error.Message, 2); }
        }
        return result;
    }
}

public static class Board
{
    private static string Cell(string value)
    {
        var output = new StringBuilder();
        foreach (Rune rune in value.EnumerateRunes())
        {
            var category = Rune.GetUnicodeCategory(rune);
            if (rune.Value is 10 or 13) output.Append(' ');
            else if (category is UnicodeCategory.Control or UnicodeCategory.Format or UnicodeCategory.LineSeparator or UnicodeCategory.ParagraphSeparator)
                output.Append("&#92;u").Append(rune.Value.ToString("x4", CultureInfo.InvariantCulture));
            else if (rune.IsAscii && "&<>|\x60[]*_\\".Contains((char)rune.Value))
                output.Append("&#").Append(rune.Value).Append(';');
            else output.Append(rune);
        }
        return output.ToString();
    }
    public static string Render(Dictionary<string, JsonObject> issues, IReadOnlyDictionary<string, JsonObject> epics,
        string generated)
    {
        var keys = epics.Keys.Order(StringComparer.Ordinal).Select(key => (string?)key).Append(null).ToList();
        string Name(string? key) => key is null ? "No epic" : Cell(Model.Field(epics[key], "title")) + " (" + key + ")";
        List<JsonObject> Members(string? key) => Model.Ordered(issues).Where(issue => Model.Epic(issue) == key).ToList();
        var lines = new List<string> { "# Beadcrumbs board", "", "Generated at " + generated + ".", "",
            "Snapshot of the issue store. Regenerate with --board. Manual edits are replaced.", "",
            "## Summary", "", "| Epic | Ready | Blocked | Claimed | Closed |", "| --- | --- | --- | --- | --- |" };
        foreach (var key in keys)
        {
            var group = Members(key);
            var counts = Model.Statuses.Select(state => group.Count(issue => Model.Status(issue, issues) == state));
            lines.Add("| " + Name(key) + " | " + string.Join(" | ", counts) + " |");
        }
        lines.Add("");
        foreach (var key in keys)
        {
            lines.Add("## " + Name(key)); lines.Add("");
            var group = Members(key);
            if (group.Count == 0) { lines.Add("No issues."); lines.Add(""); continue; }
            lines.Add("| Status | ID | Type | Priority | Title | Agent | Blockers |");
            lines.Add("| --- | --- | --- | --- | --- | --- | --- |");
            foreach (var state in Model.Statuses)
                foreach (var issue in group.Where(issue => Model.Status(issue, issues) == state))
                {
                    var blockers = Model.Blockers(issue, issues);
                    string owner = issue["claim"] is JsonObject claim ? Model.Field(claim, "agent") : "—";
                    string dependencies = blockers.Count == 0 ? "—" : string.Join(", ", blockers.Select(item =>
                        Model.Field((JsonObject)item!, "id") + " (" + Model.Field((JsonObject)item!, "state") + ")"));
                    string[] cells = [state, Model.Field(issue, "id"), Model.Field(issue, "type"),
                        "P" + Model.Priority(issue).ToString(CultureInfo.InvariantCulture), Model.Field(issue, "title"), owner, dependencies];
                    lines.Add("| " + string.Join(" | ", cells.Select(Cell)) + " |");
                }
            lines.Add("");
        }
        return string.Join("\n", lines);
    }
}

public static class Commands
{
    private static JsonObject FindEpic(string key, IReadOnlyDictionary<string, JsonObject> epics) =>
        epics.TryGetValue(key, out var epic) ? epic : throw new Failure("Epic not found: " + key, 3);
    private static bool InScope(Arguments args, JsonObject issue, IReadOnlyDictionary<string, JsonObject> epics)
    {
        if (args.Options.TryGetValue("type", out var type) && Model.Field(issue, "type") != type) return false;
        if (!args.Options.TryGetValue("epic", out var epic)) return true;
        if (epic == "none") return Model.Epic(issue) is null;
        FindEpic(epic, epics);
        return Model.Epic(issue) == epic;
    }
    public static JsonNode Run(Arguments args, string root, Dictionary<string, JsonObject> issues,
        IReadOnlyDictionary<string, JsonObject> epics, IIssueCodec codec)
    {
        switch (args.Action)
        {
            case "init": return Store.Manifest();
            case "validate": return new JsonObject { ["valid"] = true, ["issue_count"] = issues.Count, ["epic_count"] = epics.Count };
            case "list":
            case "ready":
                return new JsonArray(Model.Ordered(issues).Where(issue => (args.Action == "list" ?
                    !args.Options.ContainsKey("state") || args.Get("state") == Model.Field(issue, "state") :
                    Model.Status(issue, issues) == "ready") && InScope(args, issue, epics))
                    .Select(issue => issue.DeepClone()).ToArray());
            case "blocked":
                var blocked = new JsonArray();
                foreach (var item in Model.Ordered(issues))
                    if (Model.Status(item, issues) == "blocked")
                        blocked.Add(new JsonObject { ["issue"] = item.DeepClone(), ["blockers"] = Model.Blockers(item, issues) });
                return blocked;
            case "epics":
                return new JsonArray(epics.Keys.Order(StringComparer.Ordinal).Select(key => epics[key].DeepClone()).ToArray());
            case "show-epic":
                {
                    var epic = FindEpic(args.Value, epics);
                    var members = Model.Ordered(issues).Where(issue => Model.Epic(issue) == args.Value).ToList();
                    var counts = new JsonObject();
                    foreach (var state in Model.Statuses) counts[state] = members.Count(issue => Model.Status(issue, issues) == state);
                    return new JsonObject
                    {
                        ["epic"] = epic.DeepClone(),
                        ["counts"] = counts,
                        ["issues"] = new JsonArray(members.Select(issue => issue.DeepClone()).ToArray()),
                    };
                }
            case "create-epic":
                {
                    if (epics.ContainsKey(args.Value)) throw new Failure("Epic already exists", 4);
                    Store.PathKind(Path.Combine(root, "epics", args.Value + ".json"), optional: true);
                    string created = Model.Now();
                    var epic = new JsonObject
                    {
                        ["key"] = args.Value,
                        ["title"] = args.Get("title"),
                        ["description"] = args.Get("description"),
                        ["created_at"] = created,
                        ["updated_at"] = created,
                        ["revision"] = 1L,
                    };
                    Store.SaveEpic(root, epic);
                    return epic;
                }
            case "edit-epic":
                {
                    var epic = (JsonObject)FindEpic(args.Value, epics).DeepClone();
                    if (Model.Field(epic, "description") == args.Get("description")) throw new Failure("Epic is unchanged", 4);
                    long revision = epic["revision"]!.GetValue<long>();
                    Model.Require(revision < Model.MaxRevision, "Revision exhausted");
                    epic["description"] = args.Get("description");
                    epic["updated_at"] = Model.Now();
                    epic["revision"] = revision + 1;
                    Store.SaveEpic(root, epic);
                    return epic;
                }
            case "board":
                string path = Path.Combine(Path.GetDirectoryName(root)!, "board.md");
                Store.PathKind(path, optional: true);
                string generated = Model.Now();
                Store.Publish(path, Model.Utf8.GetBytes(Board.Render(issues, epics, generated)));
                return new JsonObject
                {
                    ["path"] = path,
                    ["issue_count"] = issues.Count,
                    ["epic_count"] = epics.Count,
                    ["generated_at"] = generated,
                };
        }
        JsonObject issue;
        if (args.Action == "create")
        {
            foreach (string dep in args.Dependencies)
                if (!issues.ContainsKey(dep)) throw new Failure("Issue not found", 3);
            string? epic = args.Options.TryGetValue("epic", out var key) && key != "none"
                ? Model.Field(FindEpic(key, epics), "key") : null;
            string id;
            do { id = "bc-" + Model.Token(); } while (issues.ContainsKey(id));
            string created = Model.Now();
            issue = new JsonObject
            {
                ["id"] = id,
                ["type"] = args.Options.GetValueOrDefault("type", "task"),
                ["priority"] = args.Options.TryGetValue("priority", out var priority)
                    ? long.Parse(priority, CultureInfo.InvariantCulture) : Model.DefaultPriority,
                ["epic"] = epic,
                ["title"] = args.Value,
                ["description"] = args.Get("description"),
                ["acceptance_criteria"] = args.Get("acceptance-criteria"),
                ["state"] = "open",
                ["depends_on"] = new JsonArray(args.Dependencies.Select(id => (JsonNode?)JsonValue.Create(id)).ToArray()),
                ["claim"] = null,
                ["notes"] = new JsonArray(),
                ["created_at"] = created,
                ["updated_at"] = created,
                ["revision"] = 1L
            };
        }
        else
        {
            if (!issues.TryGetValue(args.Value, out var original)) throw new Failure("Issue not found", 3);
            if (args.Action == "show") return original.DeepClone();
            issue = (JsonObject)original.DeepClone();
            string state = Model.Field(issue, "state");
            string? target = null;
            if (args.Action == "claim")
            {
                if (Model.Status(issue, issues) != "ready") throw new Failure("Issue is not ready", 4);
            }
            else if (args.Action == "set-epic")
            {
                if (args.Get("epic") != "none") target = Model.Field(FindEpic(args.Get("epic"), epics), "key");
                if (Model.Epic(issue) == target) throw new Failure("Issue epic is unchanged", 4);
            }
            else if (args.Action is "close" or "release")
            {
                if (state != "claimed" || Model.Field((JsonObject)issue["claim"]!, "token") != args.Get("token"))
                    throw new Failure("Claim mismatch", 4);
            }
            long revision = issue["revision"]!.GetValue<long>();
            Model.Require(revision < Model.MaxRevision, "Revision exhausted");
            string updated = Model.Now();
            switch (args.Action)
            {
                case "claim":
                    issue["state"] = "claimed"; issue["claim"] = new JsonObject { ["agent"] = args.Get("agent"), ["token"] = Model.Token() }; break;
                case "note":
                    ((JsonArray)issue["notes"]!).Add(new JsonObject { ["at"] = updated, ["by"] = args.Get("agent"), ["text"] = args.Get("text") }); break;
                case "release": issue["state"] = "open"; issue["claim"] = null; break;
                case "close": issue["state"] = "closed"; issue["claim"] = null; break;
                case "set-epic": issue["epic"] = target; break;
                default: throw new Failure("Unsupported action", 2);
            }
            issue["revision"] = revision + 1; issue["updated_at"] = updated;
        }
        Model.Validate(issue);
        Store.Publish(Path.Combine(root, "issues", codec.Filename(Model.Field(issue, "id"))), codec.Encode(issue));
        return issue;
    }
}
