# TypeScript / npm client

Strict TypeScript source implements the CLI independently. IssueCodec isolates JSON encoding, commands operate on logical issues, and the Markdown renderer is pure. Node built-ins provide filesystem access and randomness. The published shape contains compiled JavaScript and declarations, with no runtime npm dependencies.

From the repository root, using Node 22+ and npm with the pinned packages cached locally

```sh
npm ci --offline --ignore-scripts --no-audit --no-fund --prefix implementations/javascript
npm test --prefix implementations/javascript
node implementations/javascript/dist/cli.js --help
```

`npm run build --prefix implementations/javascript` compiles without running tests. Native tests cover strict decoding, alternate codecs, publication failure, and process interruption around replacement. Run the shared matrix from the repository root after building all clients.

The package is private pending release review. `npm pack --prefix implementations/javascript` is not a release workflow. To inspect a local archive, run `npm pack` inside this directory after installing build dependencies. The prepack hook rebuilds it. Generated dist/, node_modules/, and archives are ignored.

Verified locally with Node 26.13.1 and TypeScript 5.9.3 on macOS. Node 22 and other operating systems still need verification.
