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
        "claim", "note", "release", "close", "board", "help", "version"];
    public static Arguments Parse(string[] argv)
    {
        var result = new Arguments();
        string[] values = ["create", "show", "claim", "note", "release", "close", "workspace", "state", "agent",
            "token", "text", "description", "description-file", "acceptance-criteria", "depends-on"];
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
                "create" => ["depends-on", "description", "description-file", "acceptance-criteria"],
                "list" => ["state"], "claim" => ["agent"], "note" => ["agent", "text"],
                "release" or "close" => ["token"], _ => []
            };
            foreach (string key in result.Options.Keys)
            {
                bool common = result.Action is not ("help" or "version") && key is "workspace" or "json";
                Model.Require(key == result.Action || specific.Contains(key) || common, "Option does not apply");
            }
            if (result.Action is "show" or "claim" or "note" or "release" or "close")
                Model.Require(Model.Matches(Model.IdPattern, result.Value), "Invalid ID");
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
    public static string Render(Dictionary<string, JsonObject> issues, string generated)
    {
        string[] names = ["Ready", "Blocked", "Claimed", "Closed"];
        var rows = names.ToDictionary(name => name, _ => new List<string>());
        foreach (var issue in Model.Ordered(issues))
        {
            var blockers = Model.Blockers(issue, issues);
            string state = Model.Field(issue, "state");
            string section = state == "open" ? blockers.Count == 0 ? "Ready" : "Blocked" : state == "claimed" ? "Claimed" : "Closed";
            string owner = issue["claim"] is JsonObject claim ? Model.Field(claim, "agent") : "—";
            string dependencies = blockers.Count == 0 ? "—" : string.Join(", ", blockers.Select(item =>
                Model.Field((JsonObject)item!, "id") + " (" + Model.Field((JsonObject)item!, "state") + ")"));
            rows[section].Add("| " + string.Join(" | ", new[] { Model.Field(issue, "id"), Model.Field(issue, "title"), owner, dependencies }.Select(Cell)) + " |");
        }
        var lines = new List<string> { "# Beadcrumbs board", "", "Generated at " + generated + ".", "",
            "Snapshot of the issue store. Regenerate with --board. Manual edits are replaced.", "" };
        foreach (string name in names)
        {
            lines.Add("## " + name + " (" + rows[name].Count + ")"); lines.Add("");
            if (rows[name].Count == 0) lines.Add("No issues.");
            else
            {
                lines.Add("| ID | Title | Agent | Blockers |"); lines.Add("| --- | --- | --- | --- |");
                lines.AddRange(rows[name]);
            }
            lines.Add("");
        }
        return string.Join("\n", lines);
    }
}

public static class Commands
{
    public static JsonNode Run(Arguments args, string root, Dictionary<string, JsonObject> issues, IIssueCodec codec)
    {
        switch (args.Action)
        {
            case "init": return Store.Manifest();
            case "validate": return new JsonObject { ["valid"] = true, ["issue_count"] = issues.Count };
            case "list":
            case "ready":
                return new JsonArray(Model.Ordered(issues).Where(issue => args.Action == "list" ?
                    !args.Options.ContainsKey("state") || args.Get("state") == Model.Field(issue, "state") :
                    Model.Field(issue, "state") == "open" && Model.Blockers(issue, issues).Count == 0)
                    .Select(issue => issue.DeepClone()).ToArray());
            case "blocked":
                var blocked = new JsonArray();
                foreach (var item in Model.Ordered(issues))
                {
                    var dependencies = Model.Blockers(item, issues);
                    if (Model.Field(item, "state") == "open" && dependencies.Count > 0)
                        blocked.Add(new JsonObject { ["issue"] = item.DeepClone(), ["blockers"] = dependencies });
                }
                return blocked;
            case "board":
                string path = Path.Combine(Path.GetDirectoryName(root)!, "board.md");
                Store.PathKind(path, optional: true);
                string generated = Model.Now();
                Store.Publish(path, Model.Utf8.GetBytes(Board.Render(issues, generated)));
                return new JsonObject { ["path"] = path, ["issue_count"] = issues.Count, ["generated_at"] = generated };
        }
        JsonObject issue;
        if (args.Action == "create")
        {
            foreach (string dep in args.Dependencies)
                if (!issues.ContainsKey(dep)) throw new Failure("Issue not found", 3);
            string id;
            do { id = "bc-" + Model.Token(); } while (issues.ContainsKey(id));
            string created = Model.Now();
            issue = new JsonObject
            {
                ["id"] = id, ["title"] = args.Value, ["description"] = args.Get("description"),
                ["acceptance_criteria"] = args.Get("acceptance-criteria"), ["state"] = "open",
                ["depends_on"] = new JsonArray(args.Dependencies.Select(id => (JsonNode?)JsonValue.Create(id)).ToArray()),
                ["claim"] = null, ["notes"] = new JsonArray(), ["created_at"] = created, ["updated_at"] = created, ["revision"] = 1L
            };
        }
        else
        {
            if (!issues.TryGetValue(args.Value, out var original)) throw new Failure("Issue not found", 3);
            if (args.Action == "show") return original.DeepClone();
            issue = (JsonObject)original.DeepClone();
            string state = Model.Field(issue, "state");
            if (args.Action == "claim")
            {
                if (state != "open" || Model.Blockers(issue, issues).Count > 0) throw new Failure("Issue is not ready", 4);
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
                default: throw new Failure("Unsupported action", 2);
            }
            issue["revision"] = revision + 1; issue["updated_at"] = updated;
        }
        Model.Validate(issue);
        Store.Publish(Path.Combine(root, "issues", codec.Filename(Model.Field(issue, "id"))), codec.Encode(issue));
        return issue;
    }
}
