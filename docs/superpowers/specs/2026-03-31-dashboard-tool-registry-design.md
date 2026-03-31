# Design: Dashboard Tool Registry via ConfigMap

**Date**: 2026-03-31
**Branch**: feature/dashboard-tool-registry
**Status**: Approved

## Goal

Expose the list of injectable tools to the Che Dashboard so tools can be selected and pre-injected during workspace creation, before the DevWorkspace CR is submitted to the cluster.

## Context

Currently, `inject-tool` is a Python3 CLI that patches a **running** DevWorkspace CR at runtime from inside the workspace terminal. The tool registry (list of tools, images, env vars, setup commands) is hardcoded in `inject-tool.py`. There is no Dashboard integration.

## Design

### Source of Truth: `inject-tool/registry.json`

A new file `inject-tool/registry.json` is committed to the repository. It becomes the single source of truth for all tool metadata and patch data, replacing the hardcoded `TOOLS`, `TOOL_ENV`, and `TOOL_SETUP` dicts in `inject-tool.py`.

#### Format

```json
{
  "infrastructure": {
    "patch": [
      {
        "op": "add",
        "path": "/spec/template/components/-",
        "value": { "name": "injected-tools", "volume": {} }
      }
    ]
  },
  "tools": {
    "opencode": {
      "description": "AI coding assistant by OpenCode",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "inject-opencode",
            "container": {
              "image": "quay.io/okurinny/tools-injector/opencode:next",
              "command": ["sh", "-c", "cp /usr/local/bin/opencode /injected-tools/bin/opencode"],
              "volumeMounts": [{ "name": "injected-tools", "mountPath": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "mountPath": "/injected-tools" }],
        "env": [],
        "postStart": "export PATH=$PATH:/injected-tools/bin"
      }
    },
    "claude-code": {
      "description": "Claude Code AI assistant by Anthropic",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "inject-claude-code",
            "container": {
              "image": "quay.io/okurinny/tools-injector/claude-code:next",
              "command": ["sh", "-c", "cp /usr/local/bin/claude /injected-tools/bin/claude"],
              "volumeMounts": [{ "name": "injected-tools", "mountPath": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "mountPath": "/injected-tools" }],
        "env": [{ "name": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "value": "1" }],
        "postStart": "export PATH=$PATH:/injected-tools/bin"
      }
    }
  }
}
```

**Top-level keys:**
- `infrastructure.patch` — RFC 6902 JSON Patch ops to add the shared `injected-tools` volume component; applied once regardless of how many tools are selected
- `tools.<name>.description` — human-readable description for Dashboard UI
- `tools.<name>.patch` — RFC 6902 JSON Patch ops to add the tool's init container component; append-only (`/-`), no index-based ops
- `tools.<name>.editor` — structured data for Dashboard to inject into the editor container:
  - `volumeMounts` — mounts to add to the editor container
  - `env` — env vars to add to the editor container
  - `postStart` — shell command string to append to the editor's postStart lifecycle hook (multiple tools' postStart commands are concatenated with `&&`)

The `patch` arrays use only append operations (`/spec/template/components/-`) and are therefore safe to apply to any DevWorkspace structure without knowing component indices ahead of time. The `editor` section is intentionally structured (not raw JSON Patch) so the Dashboard — which already knows the editor component — can apply it without index resolution.

### ConfigMaps created by `setup.sh`

`setup.sh <namespace>` creates two ConfigMaps:

**1. `inject-tool`** (existing, updated)
Adds `registry.json` as a new key. Auto-mounted into every workspace at `/usr/local/bin/registry.json` via existing DWO automount labels.

```
inject-tool        → /usr/local/bin/inject-tool      (bash shim)
inject-tool.py     → /usr/local/bin/inject-tool.py   (Python3 CLI)
registry.json      → /usr/local/bin/registry.json    (tool registry)
```

**2. `tools-injector-registry`** (new)
Contains only `registry.json`. Well-known name for Dashboard discovery. No DWO automount labels — this ConfigMap is for cluster-level consumption, not workspace injection.

### Dashboard Integration

At workspace creation time, the Dashboard:

1. Reads `tools-injector-registry` ConfigMap → parses `registry.json`
2. Presents tool picker using `tools[*]` name + description
3. For each selected tool:
   - Applies `infrastructure.patch` once (regardless of how many tools are selected — deduplication is the Dashboard's responsibility)
   - Applies `tools[tool].patch` (init container component)
   - Injects `tools[tool].editor` into the editor container using its existing knowledge of the editor component (no index guessing)
4. Submits the patched DevWorkspace CR to the cluster — workspace starts with tools already present, no restart needed

### `inject-tool.py` Changes

The hardcoded `TOOLS`, `TOOL_ENV`, `TOOL_SETUP` dicts are removed. At startup, `inject-tool.py` loads `registry.json` from the same directory as the script (typically `/usr/local/bin/registry.json`). Override path via `INJECT_TOOL_REGISTRY_FILE` env var (useful for testing).

**Image override** — `INJECT_TOOL_REGISTRY` and `INJECT_TOOL_TAG` env vars remain supported. When set, inject-tool.py post-processes each tool's `patch` to substitute the image field in the init container, so custom registries/tags work without modifying registry.json.

**Patching flow** (unchanged externally, simplified internally):
1. Load `registry.json`
2. Fetch DevWorkspace CR from Kubernetes API
3. Find editor component index (dynamic, same as today)
4. First tool: apply `infrastructure.patch` (shared volume)
5. Per tool: apply `tool.patch` (init container component)
6. Per tool: resolve `tool.editor` → add volumeMount, env vars, postStart to editor using the resolved index

`build_inject_ops()` shrinks significantly — init container specs come from `tool.patch` in registry.json rather than being constructed inline in Python.

## Files Changed

| File | Change |
|------|--------|
| `inject-tool/registry.json` | New — source of truth for tool registry |
| `inject-tool/inject-tool.py` | Remove hardcoded dicts; load registry.json at startup |
| `inject-tool/setup.sh` | Create `tools-injector-registry` ConfigMap; add registry.json to `inject-tool` ConfigMap |

## Non-Goals

- Implementing the Dashboard UI tool picker (that's a Che Dashboard change)
- Hot-inject flow changes (stays single-tool, reads from registry.json the same way)
- RBAC changes — inject-tool.py reads registry.json from disk, no new Kubernetes API permissions needed
