using System.Runtime.InteropServices;
using System.Text.Json.Nodes;

namespace Beadcrumbs;

public static class Store
{
    // System.Native uses a platform-independent FileStatus layout.
    // Layout source: dotnet/runtime src/native/libs/System.Native/pal_io.h.
    [StructLayout(LayoutKind.Explicit, Size = 128)]
    private struct FileStatus
    {
        [FieldOffset(4)] public int Mode;
    }
    [DllImport("System.Native", EntryPoint = "SystemNative_LStat", SetLastError = true)]
    private static extern int LStat([MarshalAs(UnmanagedType.LPUTF8Str)] string path, out FileStatus status);

    [DllImport("libc", SetLastError = true, EntryPoint = "mkdir")]
    private static extern int UnixMkdir(string path, uint mode);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool CreateDirectoryW(string path, IntPtr security);

    public static bool PathKind(string path, bool directory = false, bool optional = false)
    {
        FileAttributes attributes;
        try { attributes = File.GetAttributes(path); }
        catch (FileNotFoundException) when (optional) { return false; }
        catch (DirectoryNotFoundException) when (optional) { return false; }
        Model.Require((attributes & FileAttributes.ReparsePoint) == 0, "Linked protocol path");
        Model.Require(((attributes & FileAttributes.Directory) != 0) == directory, "Unexpected path type");
        if (!OperatingSystem.IsWindows())
        {
            if (LStat(path, out var status) != 0) throw new IOException("Cannot inspect file type");
            Model.Require((status.Mode & 0xf000) == (directory ? 0x4000 : 0x8000), "Unexpected Unix file type");
        }
        return true;
    }
    private static void MakeDirectory(string path)
    {
        if (OperatingSystem.IsWindows()) Directory.CreateDirectory(path);
        else Directory.CreateDirectory(path, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        PathKind(path, true);
    }
    private static void Acquire(string path)
    {
        bool success = OperatingSystem.IsWindows() ? CreateDirectoryW(path, IntPtr.Zero) : UnixMkdir(path, 448) == 0;
        if (success) return;
        int code = Marshal.GetLastPInvokeError();
        if (code == (OperatingSystem.IsWindows() ? 183 : 17))
        {
            // The holder may remove the lock before we inspect it; that is still busy.
            PathKind(path, true, true);
            throw new Failure("Store is busy", 5);
        }
        throw new IOException("Cannot create lock, OS error " + code);
    }
    public static JsonObject Manifest() => new() { ["format"] = "beadcrumbs", ["version"] = 1 };
    public static bool ReadManifest(string root)
    {
        string path = Path.Combine(root, "store.json");
        if (!PathKind(path, optional: true)) return false;
        var value = JsonWire.Decode(File.ReadAllBytes(path));
        Model.Require(Model.Field(value, "format") == "beadcrumbs" &&
            value["version"] is JsonValue version && version.TryGetValue<int>(out var number) && number == 1,
            "Unsupported store version or format");
        Model.Fields(value, "format", "version");
        return true;
    }
    public static T Locked<T>(string root, bool initialize, Func<T> action)
    {
        if (initialize) MakeDirectory(root);
        PathKind(root, true);
        bool exists = ReadManifest(root);
        string lockPath = Path.Combine(root, ".writer.lock");
        if (!exists && !initialize)
        {
            if (PathKind(lockPath, true, true)) throw new Failure("Store is busy", 5);
            Model.Require(ReadManifest(root), "Store uninitialized");
        }
        Acquire(lockPath);
        try { return action(); }
        finally { Directory.Delete(lockPath); }
    }
    public static void Publish(string path, byte[] payload)
    {
        string scratch = Path.Combine(Path.GetDirectoryName(path)!, ".tmp-" + Model.Token());
        var options = new FileStreamOptions { Mode = FileMode.CreateNew, Access = FileAccess.Write, Share = FileShare.None };
        if (!OperatingSystem.IsWindows()) options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
        using (var stream = new FileStream(scratch, options))
        {
            try { stream.Write(payload); stream.Flush(true); }
            catch { stream.Dispose(); File.Delete(scratch); throw; }
        }
        try { File.Move(scratch, path, true); }
        finally { File.Delete(scratch); }
    }
    public static void Initialize(string root)
    {
        if (ReadManifest(root)) return;
        foreach (string entry in Directory.EnumerateFileSystemEntries(root))
        {
            string name = Path.GetFileName(entry);
            if (name == ".writer.lock") continue;
            if (name == "issues")
            {
                PathKind(entry, true);
                Model.Require(!Directory.EnumerateFileSystemEntries(entry).Any(), "Uninitialized issues directory is not empty");
            }
            else if (name.StartsWith(".tmp-", StringComparison.Ordinal) && Model.Matches(Model.TokenPattern, name[5..])) PathKind(entry);
            else throw new Failure("Unexpected uninitialized content");
        }
        MakeDirectory(Path.Combine(root, "issues"));
        Publish(Path.Combine(root, "store.json"), JsonWire.Encode(Manifest()));
    }
    public static Dictionary<string, JsonObject> Load(string root, IIssueCodec codec)
    {
        string directory = Path.Combine(root, "issues");
        PathKind(directory, true);
        var issues = new Dictionary<string, JsonObject>(StringComparer.Ordinal);
        foreach (string file in Directory.EnumerateFileSystemEntries(directory).Order(StringComparer.Ordinal))
        {
            string name = Path.GetFileName(file);
            if (!codec.Accepts(name)) continue;
            PathKind(file);
            var issue = codec.Decode(File.ReadAllBytes(file));
            Model.Validate(issue);
            string id = Model.Field(issue, "id");
            Model.Require(name == codec.Filename(id), "Filename mismatch");
            issues.Add(id, issue);
        }
        var counts = new Dictionary<string, int>();
        var dependents = issues.Keys.ToDictionary(id => id, _ => new List<string>());
        var queue = new Queue<string>();
        foreach (var (id, issue) in issues)
        {
            var dependencies = Model.Dependencies(issue);
            counts[id] = dependencies.Length;
            if (dependencies.Length == 0) queue.Enqueue(id);
            foreach (string dep in dependencies)
            {
                Model.Require(issues.ContainsKey(dep), "Missing dependency");
                Model.Require(Model.Field(issue, "state") == "open" || Model.Field(issues[dep], "state") == "closed",
                    "Unresolved dependency on active issue");
                dependents[dep].Add(id);
            }
        }
        int visited = 0;
        while (queue.Count > 0)
        {
            visited++;
            foreach (string id in dependents[queue.Dequeue()])
                if (--counts[id] == 0) queue.Enqueue(id);
        }
        Model.Require(visited == issues.Count, "Dependency cycle");
        return issues;
    }
}
