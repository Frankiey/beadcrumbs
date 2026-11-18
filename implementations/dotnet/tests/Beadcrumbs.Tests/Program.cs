using Beadcrumbs;
using System.Text.Json.Nodes;

static void Check(bool condition, string message) { if (!condition) throw new Exception(message); }
foreach (string invalid in new[] { """{"x":1,"x":2}""", """{"x":1.0}""", """{"x":1e0}""", """{"x":"\ud800"}""", """{"x":9007199254740992}""" })
{
    bool rejected = false;
    try { JsonWire.Decode(Model.Utf8.GetBytes(invalid)); } catch { rejected = true; }
    Check(rejected, "Accepted invalid JSON");
}
string folder = Path.Combine(Path.GetTempPath(), "beadcrumbs-dotnet-" + Model.Token());
Directory.CreateDirectory(folder);
try
{
    string root = Path.Combine(folder, ".beadcrumbs");
    var codec = new ExampleCodec();
    Store.Locked(root, true, () =>
    {
        Store.Initialize(root);
        JsonNode Call(params string[] args) => Commands.Run(Arguments.Parse(args), root, Store.Load(root, codec), Store.LoadEpics(root), codec);
        var issue = Call("--create", "Alternate");
        string id = issue["id"]!.GetValue<string>();
        var claim = Call("--claim", id, "--agent", "worker");
        Call("--note", id, "--agent", "worker", "--text", "Done");
        var closed = Call("--close", id, "--token", claim["claim"]!["token"]!.GetValue<string>());
        Check(closed["revision"]!.GetValue<long>() == 4, "Wrong revision");
        Check(closed["state"]!.GetValue<string>() == "closed", "Wrong state");
        Check(File.Exists(Path.Combine(root, "issues", id + ".example")), "Codec bypassed");
        return true;
    });
    string destination = Path.Combine(folder, "directory");
    Directory.CreateDirectory(destination);
    bool rejected = false;
    try { Store.Publish(destination, [1, 2, 3]); } catch (IOException) { rejected = true; }
    Check(rejected, "Replacement should fail");
    Check(!Directory.EnumerateFiles(folder, ".tmp-*").Any(), "Scratch file remains");
}
finally { Directory.Delete(folder, true); }
Console.WriteLine("Passed strict JSON, alternate-codec lifecycle, and publication-failure checks.");

sealed class ExampleCodec : IIssueCodec
{
    public bool Accepts(string name) => name.EndsWith(".example", StringComparison.Ordinal);
    public string Filename(string id) => id + ".example";
    public byte[] Encode(JsonObject issue) => [.. Model.Utf8.GetBytes("example\n"), .. JsonWire.Encode(issue)];
    public JsonObject Decode(byte[] bytes)
    {
        if (Model.Utf8.GetString(bytes[..8]) != "example\n") throw new Failure("Invalid example bytes");
        return JsonWire.Decode(bytes[8..]);
    }
}
