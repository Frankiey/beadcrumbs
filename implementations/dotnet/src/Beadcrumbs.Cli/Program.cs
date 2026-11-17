using System.Text.Json;
using Beadcrumbs;

try
{
    var arguments = Arguments.Parse(args);
    if (arguments.Action == "help")
    {
        Console.WriteLine("Beadcrumbs offline issue tracker\n--" + string.Join(" --", Arguments.Actions));
        return 0;
    }
    if (arguments.Action == "version") { Console.WriteLine("beadcrumbs 0.1.0"); return 0; }
    string workspace = Path.GetFullPath(arguments.Get("workspace") is "" ? "." : arguments.Get("workspace"));
    // Resolve every existing workspace component, including ancestor symlinks.
    string resolved = Path.GetPathRoot(workspace)!;
    foreach (string part in workspace[resolved.Length..].Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
    {
        var directory = new DirectoryInfo(Path.Combine(resolved, part));
        resolved = directory.ResolveLinkTarget(true)?.FullName ?? directory.FullName;
    }
    Store.PathKind(resolved, true);
    string root = Path.Combine(resolved, ".beadcrumbs");
    var codec = new JsonIssueCodec();
    var result = Store.Locked(root, arguments.Action == "init", () =>
    {
        if (arguments.Action == "init") Store.Initialize(root);
        Model.Require(Store.ReadManifest(root), "Store uninitialized");
        return Commands.Run(arguments, root, Store.Load(root, codec), codec);
    });
    Console.WriteLine(result.ToJsonString(arguments.Options.ContainsKey("json") ? null : Model.Pretty));
    return 0;
}
catch (Exception error) when (error is not OutOfMemoryException)
{
    Console.Error.WriteLine("beadcrumbs: " + JsonSerializer.Serialize(error.Message));
    return error is Failure failure ? failure.Code : 1;
}
