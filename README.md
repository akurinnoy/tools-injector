# tools-injector

Container images and `inject-tool` CLI for injecting AI CLI tools into Eclipse Che DevWorkspaces via init containers.

## Tool Images

| Tool | Pattern | Image | Architectures |
|------|---------|-------|---------------|
| opencode | init | `quay.io/akurinnoy/tools-injector/opencode:next` | amd64, arm64 |
| goose | init | `quay.io/akurinnoy/tools-injector/goose:next` | amd64, arm64 |
| claude-code | init | `quay.io/akurinnoy/tools-injector/claude-code:next` | amd64, arm64 |
| gemini-cli | bundle | `quay.io/akurinnoy/tools-injector/gemini-cli:next` | amd64, arm64 |
| kilocode | bundle | `quay.io/akurinnoy/tools-injector/kilocode:next` | amd64, arm64 |
| tmux | init | `quay.io/akurinnoy/tools-injector/tmux:next` | amd64, arm64 |
| python3 | init | `quay.io/akurinnoy/tools-injector/python3:next` | amd64, arm64 |

**Init pattern**: Single binary copied to a shared volume via preStart init container.
**Bundle pattern**: Node.js tool + runtime bundled at `/opt/<tool>/`, copied via init container.

## Setup

Deploy `inject-tool` and the tool registry to a Che namespace (requires `kubectl` or `oc` with cluster access):

```bash
inject-tool/setup.sh <namespace>
```

This creates two ConfigMaps in the namespace:
- **`inject-tool`** — automounted into every workspace at `/usr/local/bin/` via DWO labels
- **`tools-injector-registry`** — exposes the tool registry to Che Dashboard (labeled `app.kubernetes.io/part-of=tools-injector`)

After setup, `inject-tool` is available in every new or restarted workspace in that namespace.

## inject-tool CLI

A Python3 CLI (deployed via ConfigMap) that automates tool injection into running DevWorkspaces:

```bash
inject-tool list              # List available tools
inject-tool <tool>            # Inject a tool
inject-tool remove <tool>     # Remove an injected tool
inject-tool <tool> --hot      # Hot-inject into running workspace
```

Features:
- Auto PATH setup via `$HOME/.bashrc`
- Auto env vars per tool (TOOL_ENV registry)
- Auto config pre-seeding (TOOL_SETUP registry)
- Auto memory bump +512Mi for bundle tools

See [inject-tool/README.md](inject-tool/README.md) for details.

### Project-Scoped Tool Injection

To declare tools for automatic injection when a workspace starts, create `.che/inject-tools.json` in your project repository:

```json
{
  "tools": [
    "opencode",
    "tmux",
    {
      "name": "dev-tools",
      "image": "quay.io/myorg/my-project-tools:latest",
      "binaries": [
        { "src": "/usr/bin/git", "binary": "git" },
        { "src": "/usr/bin/jq", "binary": "jq" }
      ]
    }
  ]
}
```

**Tool formats:**
- **String** (registry tool): `"opencode"` — looks up the tool in `inject-tool/registry.json`
- **Object** (custom tool): Full tool definition with required fields `name`, `image`, `binaries`

**Required fields for custom tools:**
- `name` — tool identifier (used for init container and volume mount names)
- `image` — container image with the binaries
- `binaries` — array of `{ "src": "<path-in-image>", "binary": "<name-in-PATH>" }` objects

**Optional fields for custom tools:**
- `description` — human-readable description (shown in `inject-tool list`)
- `env` — array of `{ "name": "<VAR>", "value": "<value>" }` objects for environment variables
- `postStart` — shell command to run after injection (e.g., config file generation)
- `memoryLimit` — memory bump for the editor container (e.g., `"512Mi"` for bundle tools)

**Usage:**

```bash
inject-tool init          # Scan /projects/*/.che/inject-tools.json and inject declared tools
inject-tool init --dry-run # Preview what would be injected without applying changes
```

The `init` subcommand is idempotent — safe to run multiple times. It only triggers a workspace restart if new tools are added.

Override the config file path with the `INJECT_TOOLS_CONFIG` environment variable:

```bash
INJECT_TOOLS_CONFIG=/path/to/custom-config.json inject-tool init
```

## Building

```bash
# Build a single tool for current platform
make docker-build-local-opencode

# Build multi-arch (amd64+arm64), no push
make docker-build-opencode

# Build and push multi-arch (requires docker buildx + registry login)
make docker-opencode

# Build all tools
make docker-build-all
```

## Vertex AI Authentication

See [docs/vertex-ai-setup.md](docs/vertex-ai-setup.md) for setting up Google Cloud ADC authentication in DevWorkspaces.

## License

[EPL-2.0](LICENSE)
