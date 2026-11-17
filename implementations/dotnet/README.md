# .NET client

The solution contains the CLI and a dependency-free console test harness. IIssueCodec isolates encoding, logical records use JsonObject, and the store owns publication. Board rendering is separate from filesystem access.

From the repository root with .NET SDK 11

```sh
DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false dotnet build implementations/dotnet/Beadcrumbs.sln --disable-build-servers
DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet run --project implementations/dotnet/tests/Beadcrumbs.Tests --no-build
DOTNET_CLI_TELEMETRY_OPTOUT=1 dotnet implementations/dotnet/src/Beadcrumbs.Cli/bin/Debug/net11.0/Beadcrumbs.Cli.dll --help
```

NuGet.Config clears package sources. There are no NuGet dependencies and the installed SDK supplies framework references. Native tests cover strict decoding, alternate-codec lifecycle, and failed replacement cleanup. bin/, obj/, and .cli-home/ are ignored.

Exclusive lock creation uses native mkdir/CreateDirectoryW. Unix file-type checks use the installed runtime's System.Native lstat shim to reject special files such as FIFOs without opening them. This private runtime interface is a compatibility consideration when retargeting the framework and must be tested then. Windows uses file attributes and rejects reparse points.

Verified locally with SDK 11.0.100 on macOS, including FIFO rejection. Linux and Windows behavior remains unverified. This is a framework-dependent CLI scaffold, not yet a published dotnet tool package.
