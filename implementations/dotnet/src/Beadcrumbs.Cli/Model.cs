using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Beadcrumbs;

public sealed class Failure(string message, int code = 1) : Exception(message)
{
    public int Code { get; } = code;
}

public static class Model
{
    public const long MaxRevision = 9007199254740991;
    public const string TokenPattern = "[0-9a-f]{12}4[0-9a-f]{3}[89ab][0-9a-f]{15}";
    public const string IdPattern = "bc-" + TokenPattern;
    public const string AgentPattern = "[A-Za-z0-9][A-Za-z0-9._-]{0,63}";
    public static readonly UTF8Encoding Utf8 = new(false, true);
    public static readonly JsonSerializerOptions Pretty = new() { WriteIndented = true };

    public static void Require(bool condition, string message)
    {
        if (!condition) throw new Failure(message);
    }
    public static bool Matches(string pattern, string value) =>
        Regex.IsMatch(value, "\\A(?:" + pattern + ")\\z", RegexOptions.CultureInvariant);
    public static string Text(JsonNode? value) =>
        value is JsonValue scalar && scalar.TryGetValue<string>(out var text)
            ? text : throw new Failure("Expected text");
    public static string Field(JsonObject issue, string key) => Text(issue[key]);
    public static string Now() => DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
    public static string Token() => Guid.NewGuid().ToString("N");
    public static void Fields(JsonObject value, params string[] fields)
    {
        Require(value.Count == fields.Length && fields.All(value.ContainsKey), "Invalid object fields");
    }
    public static void Scalar(string value)
    {
        try { Utf8.GetByteCount(value); }
        catch (EncoderFallbackException) { throw new Failure("Unpaired Unicode surrogate"); }
    }
    public static void Timestamp(string value)
    {
        Require(DateTime.TryParseExact(value, "yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture,
            DateTimeStyles.None, out _), "Invalid timestamp");
    }
    public static void Validate(JsonObject issue)
    {
        Fields(issue, "id", "title", "description", "acceptance_criteria", "state", "depends_on",
            "claim", "notes", "created_at", "updated_at", "revision");
        foreach (var key in new[] { "id", "title", "description", "acceptance_criteria", "state", "created_at", "updated_at" })
            Scalar(Field(issue, key));
        Require(Matches(IdPattern, Field(issue, "id")), "Invalid ID");
        Require(Field(issue, "title").Length > 0, "Empty title");
        var state = Field(issue, "state");
        Require(state is "open" or "claimed" or "closed", "Invalid state");
        var dependencies = issue["depends_on"] as JsonArray ?? throw new Failure("Invalid dependencies");
        var ids = dependencies.Select(Text).ToArray();
        Require(ids.All(id => Matches(IdPattern, id)) && ids.Distinct().Count() == ids.Length, "Invalid dependency");
        if (state == "claimed")
        {
            var claim = issue["claim"] as JsonObject ?? throw new Failure("Missing claim");
            Fields(claim, "agent", "token");
            Require(Matches(AgentPattern, Field(claim, "agent")) && Matches(TokenPattern, Field(claim, "token")), "Invalid claim");
        }
        else Require(issue["claim"] is null, "Unexpected claim");
        var notes = issue["notes"] as JsonArray ?? throw new Failure("Invalid notes");
        foreach (var value in notes)
        {
            var note = value as JsonObject ?? throw new Failure("Invalid note");
            Fields(note, "at", "by", "text");
            Timestamp(Field(note, "at"));
            Require(Matches(AgentPattern, Field(note, "by")) && Field(note, "text").Length > 0, "Invalid note");
            Scalar(Field(note, "text"));
        }
        Timestamp(Field(issue, "created_at"));
        Timestamp(Field(issue, "updated_at"));
        Require(issue["revision"] is JsonValue revision && revision.TryGetValue<long>(out var number) &&
            number >= 1 && number <= MaxRevision, "Invalid revision");
    }
    public static string[] Dependencies(JsonObject issue) => ((JsonArray)issue["depends_on"]!).Select(Text).ToArray();
    public static JsonArray Blockers(JsonObject issue, Dictionary<string, JsonObject> issues)
    {
        var result = new JsonArray();
        foreach (var id in Dependencies(issue))
            if (Field(issues[id], "state") != "closed")
                result.Add(new JsonObject { ["id"] = id, ["state"] = Field(issues[id], "state") });
        return result;
    }
    public static IEnumerable<JsonObject> Ordered(Dictionary<string, JsonObject> issues) =>
        issues.Values.OrderBy(issue => Field(issue, "created_at"), StringComparer.Ordinal)
            .ThenBy(issue => Field(issue, "id"), StringComparer.Ordinal);
}

public interface IIssueCodec
{
    bool Accepts(string filename);
    string Filename(string id);
    JsonObject Decode(byte[] payload);
    byte[] Encode(JsonObject issue);
}

public sealed class JsonIssueCodec : IIssueCodec
{
    public bool Accepts(string filename) => filename.EndsWith(".json", StringComparison.Ordinal);
    public string Filename(string id)
    {
        Model.Require(Model.Matches(Model.IdPattern, id), "Invalid ID");
        return id + ".json";
    }
    public JsonObject Decode(byte[] payload) => JsonWire.Decode(payload);
    public byte[] Encode(JsonObject issue) => JsonWire.Encode(issue);
}

public static class JsonWire
{
    private static void Check(JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                var keys = new HashSet<string>(StringComparer.Ordinal);
                foreach (var property in value.EnumerateObject())
                {
                    Model.Scalar(property.Name);
                    Model.Require(keys.Add(property.Name), "Duplicate JSON key");
                    Check(property.Value);
                }
                break;
            case JsonValueKind.Array:
                foreach (var item in value.EnumerateArray()) Check(item);
                break;
            case JsonValueKind.String:
                Model.Scalar(value.GetString()!);
                break;
            case JsonValueKind.Number:
                var raw = value.GetRawText();
                Model.Require(!raw.Contains('.') && !raw.Contains('e') && !raw.Contains('E') &&
                    value.TryGetInt64(out var number) && number <= Model.MaxRevision && number >= -Model.MaxRevision,
                    "Invalid integer lexical form or range");
                break;
        }
    }
    public static string DecodeUtf8(byte[] bytes)
    {
        Model.Require(!(bytes.Length >= 3 && bytes[0] == 239 && bytes[1] == 187 && bytes[2] == 191), "UTF-8 BOM is invalid");
        return Model.Utf8.GetString(bytes);
    }
    public static JsonObject Decode(byte[] bytes)
    {
        var text = DecodeUtf8(bytes);
        using var document = JsonDocument.Parse(text);
        Check(document.RootElement);
        return JsonNode.Parse(text) as JsonObject ?? throw new Failure("Expected object");
    }
    public static byte[] Encode(JsonObject value) => Model.Utf8.GetBytes(value.ToJsonString(Model.Pretty) + "\n");
}
