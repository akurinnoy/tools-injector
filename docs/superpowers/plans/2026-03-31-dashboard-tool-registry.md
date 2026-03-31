# Dashboard Tool Registry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `inject-tool/registry.json` as the single source of truth for tool metadata and patches, expose it via a `tools-injector-registry` ConfigMap for Dashboard consumption, and migrate `inject-tool.py` off its hardcoded dicts.

**Architecture:** `registry.json` holds per-tool init container patch ops (RFC 6902, append-only) plus editor-specific structured data (volumeMounts, env, postStart). `setup.sh` creates two ConfigMaps: the existing `inject-tool` (updated to include `registry.json`) and a new `tools-injector-registry` (registry.json only, for Dashboard). `inject-tool.py` loads `registry.json` from disk at startup, replacing the hardcoded `TOOLS`, `TOOL_ENV`, `TOOL_SETUP` dicts while preserving all runtime behaviour including image overrides via env vars.

**Tech Stack:** Python 3, JSON (stdlib), Bash, kubectl, Kubernetes ConfigMap, RFC 6902 JSON Patch

---

### Task 1: Create `inject-tool/registry.json`

**Files:**
- Create: `inject-tool/registry.json`

- [ ] **Step 1: Write `inject-tool/registry.json`**

Create the file with the following content (all 7 tools):

```json
{
  "registry": "quay.io/okurinny",
  "tag": "next",
  "infrastructure": {
    "patch": [
      {
        "op": "add",
        "path": "/spec/template/components/-",
        "value": { "name": "injected-tools", "volume": { "size": "256Mi" } }
      }
    ]
  },
  "tools": {
    "opencode": {
      "description": "AI coding assistant by OpenCode",
      "pattern": "init",
      "src": "/usr/local/bin/opencode",
      "binary": "opencode",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "opencode-injector",
            "container": {
              "image": "quay.io/okurinny/tools-injector/opencode:next",
              "command": ["/bin/cp"],
              "args": ["/usr/local/bin/opencode", "/injected-tools/opencode"],
              "memoryLimit": "128Mi",
              "mountSources": false,
              "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
        "env": [],
        "postStart": ""
      }
    },
    "goose": {
      "description": "AI coding assistant by Block",
      "pattern": "init",
      "src": "/usr/local/bin/goose",
      "binary": "goose",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "goose-injector",
            "container": {
              "image": "quay.io/okurinny/tools-injector/goose:next",
              "command": ["/bin/cp"],
              "args": ["/usr/local/bin/goose", "/injected-tools/goose"],
              "memoryLimit": "128Mi",
              "mountSources": false,
              "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
        "env": [],
        "postStart": ""
      }
    },
    "claude-code": {
      "description": "Claude Code AI assistant by Anthropic",
      "pattern": "init",
      "src": "/usr/local/bin/claude",
      "binary": "claude",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "claude-code-injector",
            "container": {
              "image": "quay.io/okurinny/tools-injector/claude-code:next",
              "command": ["/bin/cp"],
              "args": ["/usr/local/bin/claude", "/injected-tools/claude"],
              "memoryLimit": "128Mi",
              "mountSources": false,
              "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
        "env": [{ "name": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "value": "1" }],
        "postStart": ""
      }
    },
    "kilocode": {
      "description": "Kilo Code AI assistant (VS Code extension with AI backend)",
      "pattern": "bundle",
      "src": "/opt/kilocode",
      "binary": "kilo",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "kilocode-injector",
            "container": {
              "image": "quay.io/okurinny/tools-injector/kilocode:next",
              "command": ["/bin/sh"],
              "args": ["-c", "cp -a /opt/kilocode/. /injected-tools/kilocode/"],
              "memoryLimit": "256Mi",
              "mountSources": false,
              "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
        "env": [],
        "postStart": ""
      }
    },
    "gemini-cli": {
      "description": "Gemini CLI AI assistant by Google",
      "pattern": "bundle",
      "src": "/opt/gemini-cli",
      "binary": "gemini",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "gemini-cli-injector",
            "container": {
              "image": "quay.io/okurinny/tools-injector/gemini-cli:next",
              "command": ["/bin/sh"],
              "args": ["-c", "cp -a /opt/gemini-cli/. /injected-tools/gemini-cli/"],
              "memoryLimit": "256Mi",
              "mountSources": false,
              "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
        "env": [{ "name": "GEMINI_CLI_HOME", "value": "/tmp/gemini-home" }],
        "postStart": "mkdir -p /tmp/gemini-home/.gemini && echo '{\"projects\":{}}' > /tmp/gemini-home/.gemini/projects.json"
      }
    },
    "tmux": {
      "description": "Terminal multiplexer",
      "pattern": "init",
      "src": "/usr/local/bin/tmux",
      "binary": "tmux",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "tmux-injector",
            "container": {
              "image": "quay.io/okurinny/tools-injector/tmux:next",
              "command": ["/bin/cp"],
              "args": ["/usr/local/bin/tmux", "/injected-tools/tmux"],
              "memoryLimit": "128Mi",
              "mountSources": false,
              "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
        "env": [],
        "postStart": ""
      }
    },
    "python3": {
      "description": "Python3 interpreter",
      "pattern": "init",
      "src": "/usr/local/bin/python3",
      "binary": "python3",
      "patch": [
        {
          "op": "add",
          "path": "/spec/template/components/-",
          "value": {
            "name": "python3-injector",
            "container": {
              "image": "quay.io/okurinny/tools-injector/python3:next",
              "command": ["/bin/cp"],
              "args": ["/usr/local/bin/python3", "/injected-tools/python3"],
              "memoryLimit": "128Mi",
              "mountSources": false,
              "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
            }
          }
        }
      ],
      "editor": {
        "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
        "env": [],
        "postStart": ""
      }
    }
  }
}
```

- [ ] **Step 2: Validate JSON parses cleanly**

```
python3 -c "import json; d=json.load(open('inject-tool/registry.json')); print('tools:', list(d['tools'].keys()))"
```

Expected output:
```
tools: ['opencode', 'goose', 'claude-code', 'kilocode', 'gemini-cli', 'tmux', 'python3']
```

- [ ] **Step 3: Commit**

```
git add inject-tool/registry.json
git commit -s -m "feat: add registry.json as source of truth for tool registry"
```

---

### Task 2: Update `inject-tool.py` — registry loading and global helpers

**Files:**
- Modify: `inject-tool/inject-tool.py`

Remove the five hardcoded constants (`TOOLS`, `TOOL_ENV`, `TOOL_SETUP`, `REGISTRY`, `TAG`) and replace with a `load_registry()` function plus updated `tool_image()`, `validate_tools()`, and `cmd_list()`. Also add `import copy` (needed in Task 3).

- [ ] **Step 1: Add `import copy` after the existing imports block**

After line 10 (`import urllib.request`), add:
```python
import copy
```

- [ ] **Step 2: Replace the registry constants block (lines 15–35) with registry loading**

Delete everything from `TOOLS = {` through `TAG = os.environ.get(...)` and replace with:

```python
# ============================================================================
# Tool registry (loaded from registry.json at startup)
# ============================================================================
def _registry_path():
    override = os.environ.get("INJECT_TOOL_REGISTRY_FILE")
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "registry.json")


def load_registry():
    path = _registry_path()
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: registry.json not found at {path}", file=sys.stderr)
        print("Set INJECT_TOOL_REGISTRY_FILE to override the path.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: registry.json is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


REGISTRY_DATA = load_registry()

_base_registry = os.environ.get("INJECT_TOOL_REGISTRY") or REGISTRY_DATA["registry"]
_base_tag = os.environ.get("INJECT_TOOL_TAG") or REGISTRY_DATA["tag"]
```

- [ ] **Step 3: Replace `tool_image()` and `validate_tools()`**

Replace:
```python
def tool_image(tool):
    return f"{REGISTRY}/tools-injector/{tool}:{TAG}"


def validate_tools(tool_names):
    for name in tool_names:
        if name not in TOOLS:
            print(f"Unknown tool: {name}\n", file=sys.stderr)
            print("Available tools:", file=sys.stderr)
            for t in sorted(TOOLS):
                print(f"  {t:<15s} {TOOLS[t]['pattern']}", file=sys.stderr)
            sys.exit(1)
```

With:
```python
def tool_image(tool):
    return f"{_base_registry}/tools-injector/{tool}:{_base_tag}"


def validate_tools(tool_names):
    tools = REGISTRY_DATA["tools"]
    for name in tool_names:
        if name not in tools:
            print(f"Unknown tool: {name}\n", file=sys.stderr)
            print("Available tools:", file=sys.stderr)
            for t in sorted(tools):
                print(f"  {t:<15s} {tools[t]['pattern']}", file=sys.stderr)
            sys.exit(1)
```

- [ ] **Step 4: Replace `cmd_list()`**

Replace:
```python
def cmd_list():
    validate_env()
    ws = fetch_workspace()
    print(f"{'Tool':<15s} {'Pattern':<10s} {'Status'}")
    print(f"{'----':<15s} {'-------':<10s} {'------'}")
    for tool in sorted(TOOLS):
        pattern = TOOLS[tool]["pattern"]
        comp_name = f"{tool}-injector"
        status = "injected" if find_component_index(ws, comp_name) is not None else "not injected"
        print(f"{tool:<15s} {pattern:<10s} {status}")
```

With:
```python
def cmd_list():
    validate_env()
    ws = fetch_workspace()
    print(f"{'Tool':<15s} {'Pattern':<10s} {'Status'}")
    print(f"{'----':<15s} {'-------':<10s} {'------'}")
    for tool in sorted(REGISTRY_DATA["tools"]):
        pattern = REGISTRY_DATA["tools"][tool]["pattern"]
        comp_name = f"{tool}-injector"
        status = "injected" if find_component_index(ws, comp_name) is not None else "not injected"
        print(f"{tool:<15s} {pattern:<10s} {status}")
```

- [ ] **Step 5: Verify the script loads without errors**

```
INJECT_TOOL_REGISTRY_FILE=inject-tool/registry.json python3 inject-tool/inject-tool.py --help
```

Expected: help text with `{inject,list,remove}` subcommands, no tracebacks.

- [ ] **Step 6: Commit**

```
git add inject-tool/inject-tool.py
git commit -s -m "feat: load tool registry from registry.json instead of hardcoded dicts"
```

---

### Task 3: Update `inject-tool.py` — patch-building functions

**Files:**
- Modify: `inject-tool/inject-tool.py`

Rewrite `build_inject_ops()` to read init container specs from `registry.json`. Update `hot_inject()`, `cmd_inject()`, `build_remove_ops()`, and the hot-remove path in `cmd_remove()`.

- [ ] **Step 1: Rewrite `build_inject_ops()`**

Replace the entire `build_inject_ops` function with:

```python
def build_inject_ops(tool, ws, skip_infra=False):
    reg_tool = REGISTRY_DATA["tools"][tool]
    pattern = reg_tool["pattern"]
    binary_name = reg_tool["binary"]
    ops = []

    editor = find_editor(ws)
    editor_idx = editor[0] if editor else None
    editor_name = editor[1] if editor else None

    # 1. Add injected-tools volume if missing
    if not skip_infra and find_component_index(ws, "injected-tools") is None:
        ops.extend(REGISTRY_DATA["infrastructure"]["patch"])

    # 2. Add injector component from registry patch (with image override)
    patch_ops = copy.deepcopy(reg_tool["patch"])
    for op in patch_ops:
        if op.get("op") == "add" and isinstance(op.get("value"), dict):
            container = op["value"].get("container", {})
            if "image" in container:
                container["image"] = tool_image(tool)
    ops.extend(patch_ops)

    # 3. Add volume mount to editor
    if editor_idx is not None and not skip_infra:
        mounts = get_components(ws)[editor_idx].get("container", {}).get("volumeMounts", [])
        has_mount = any(m.get("name") == "injected-tools" for m in mounts)
        if not has_mount:
            for vm in reg_tool["editor"]["volumeMounts"]:
                if mounts:
                    ops.append({"op": "add",
                                 "path": f"/spec/template/components/{editor_idx}/container/volumeMounts/-",
                                 "value": vm})
                else:
                    ops.append({"op": "add",
                                 "path": f"/spec/template/components/{editor_idx}/container/volumeMounts",
                                 "value": [vm]})
                    mounts = [vm]
    elif editor_idx is None and not skip_infra:
        print("WARNING: Could not find editor component. You may need to add the volume mount manually.",
              file=sys.stderr)

    # 3b. Add tool-specific env vars
    if editor_idx is not None and reg_tool["editor"]["env"]:
        env_list = get_components(ws)[editor_idx].get("container", {}).get("env")
        env_exists = env_list is not None and len(env_list) > 0
        for i, env_var in enumerate(reg_tool["editor"]["env"]):
            if not skip_infra and not env_exists and i == 0:
                ops.append({"op": "add",
                             "path": f"/spec/template/components/{editor_idx}/container/env",
                             "value": [env_var]})
                env_exists = True
            else:
                ops.append({"op": "add",
                             "path": f"/spec/template/components/{editor_idx}/container/env/-",
                             "value": env_var})

    # 3c. Memory bump for bundle tools
    if not skip_infra and editor_idx is not None and pattern == "bundle":
        current_mem = parse_memory(
            get_components(ws)[editor_idx].get("container", {}).get("memoryLimit", ""))
        if current_mem == 0:
            ops.append({"op": "add",
                         "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                         "value": "1536Mi"})
        else:
            ops.append({"op": "replace",
                         "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                         "value": f"{current_mem + 512}Mi"})

    # 4. Add apply command
    commands = ws.get("spec", {}).get("template", {}).get("commands")
    if skip_infra or commands is not None:
        ops.append({"op": "add", "path": "/spec/template/commands/-",
                     "value": {"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}})
    else:
        ops.append({"op": "add", "path": "/spec/template/commands",
                     "value": [{"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}]})

    # 5. Add preStart event
    prestart = get_events(ws).get("preStart")
    if not skip_infra and prestart is None:
        ops.append({"op": "add", "path": "/spec/template/events",
                     "value": {"preStart": [f"install-{tool}"]}})
    else:
        ops.append({"op": "add", "path": "/spec/template/events/preStart/-",
                     "value": f"install-{tool}"})

    # 6. Symlink command + postStart event
    if editor_name:
        symlink_cmd_id = f"symlink-{tool}"
        if find_command_index(ws, symlink_cmd_id) is None:
            if pattern == "init":
                symlink_target = f"/injected-tools/{binary_name}"
            else:
                symlink_target = f"/injected-tools/{tool}/bin/{binary_name}"

            path_cmd = (
                'grep -q injected-tools /etc/profile.d/injected-tools.sh 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' > /etc/profile.d/injected-tools.sh 2>/dev/null;'
                ' grep -q injected-tools "$HOME/.bashrc" 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' >> "$HOME/.bashrc" 2>/dev/null; true'
            )
            cmdline = (
                f"mkdir -p /injected-tools/bin && "
                f"ln -sf {symlink_target} /injected-tools/bin/{binary_name} && "
                f"{path_cmd}"
            )
            setup_cmd = reg_tool["editor"].get("postStart", "")
            if setup_cmd:
                cmdline = f"{setup_cmd} && {cmdline}"

            ops.append({"op": "add", "path": "/spec/template/commands/-",
                         "value": {"id": symlink_cmd_id, "exec": {
                             "component": editor_name, "commandLine": cmdline}}})

            poststart = get_events(ws).get("postStart")
            if not skip_infra and poststart is None:
                ops.append({"op": "add", "path": "/spec/template/events/postStart",
                             "value": [symlink_cmd_id]})
            else:
                ops.append({"op": "add", "path": "/spec/template/events/postStart/-",
                             "value": symlink_cmd_id})

    return ops
```

- [ ] **Step 2: Update `hot_inject()`**

Replace the first 4 lines of `hot_inject()`:
```python
def hot_inject(tool):
    t = TOOLS[tool]
    if t["pattern"] \!= "init":
        die(f"--hot is only supported for init container tools. Use 'inject-tool {tool}' (without --hot) instead.")
    if subprocess.run(["which", "oc"], capture_output=True).returncode \!= 0:
        die(f"--hot mode requires the 'oc' CLI. Use 'inject-tool {tool}' (without --hot) for default mode.")

    image = tool_image(tool)
    binary_src = t["src"]
    binary_name = t["binary"]
```

With:
```python
def hot_inject(tool):
    reg_tool = REGISTRY_DATA["tools"][tool]
    if reg_tool["pattern"] \!= "init":
        die(f"--hot is only supported for init container tools. Use 'inject-tool {tool}' (without --hot) instead.")
    if subprocess.run(["which", "oc"], capture_output=True).returncode \!= 0:
        die(f"--hot mode requires the 'oc' CLI. Use 'inject-tool {tool}' (without --hot) for default mode.")

    image = tool_image(tool)
    binary_src = reg_tool["src"]
    binary_name = reg_tool["binary"]
```

- [ ] **Step 3: Update bundle count in `cmd_inject()`**

Replace:
```python
    bundle_count = sum(1 for t in to_inject if TOOLS[t]["pattern"] == "bundle")
```

With:
```python
    bundle_count = sum(1 for t in to_inject if REGISTRY_DATA["tools"][t]["pattern"] == "bundle")
```

- [ ] **Step 4: Remove unused `t = TOOLS[tool]` line from `build_remove_ops()`**

In `build_remove_ops`, delete:
```python
    t = TOOLS[tool]
```

- [ ] **Step 5: Update hot-remove path in `cmd_remove()`**

Replace:
```python
        tool = tools[0]
        t = TOOLS[tool]
        if t["pattern"] \!= "init":
            die("--hot remove is only supported for init container tools.")
        binary_path = f"/injected-tools/{t['binary']}"
```

With:
```python
        tool = tools[0]
        reg_tool = REGISTRY_DATA["tools"][tool]
        if reg_tool["pattern"] \!= "init":
            die("--hot remove is only supported for init container tools.")
        binary_path = f"/injected-tools/{reg_tool['binary']}"
```

- [ ] **Step 6: Verify no remaining references to removed constants**

```
grep -n "TOOLS\b\|TOOL_ENV\b\|TOOL_SETUP\b" inject-tool/inject-tool.py
```

Expected: no output.

- [ ] **Step 7: Verify script loads cleanly**

```
INJECT_TOOL_REGISTRY_FILE=inject-tool/registry.json python3 inject-tool/inject-tool.py --help
```

Expected: help text, no errors.

- [ ] **Step 8: Commit**

```
git add inject-tool/inject-tool.py
git commit -s -m "feat: migrate patch-building functions to read from registry.json"
```

---

### Task 4: Update `inject-tool/setup.sh`

**Files:**
- Modify: `inject-tool/setup.sh`

Add `registry.json` to the `inject-tool` ConfigMap and create the new `tools-injector-registry` ConfigMap.

- [ ] **Step 1: Add registry.json existence check**

After the existing `inject-tool.py` check (lines 18–21), add:
```bash
[[ -f "${SCRIPT_DIR}/registry.json" ]] || {
  echo "ERROR: registry.json not found in ${SCRIPT_DIR}" >&2
  exit 1
}
```

- [ ] **Step 2: Add registry.json to the inject-tool ConfigMap**

In the `kubectl create configmap "${CM_NAME}"` block, add `--from-file=registry.json`:

```bash
kubectl create configmap "${CM_NAME}" \
  --from-file=inject-tool="${SCRIPT_DIR}/inject-tool" \
  --from-file=inject-tool.py="${SCRIPT_DIR}/inject-tool.py" \
  --from-file=registry.json="${SCRIPT_DIR}/registry.json" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -
```

- [ ] **Step 3: Create `tools-injector-registry` ConfigMap after the existing annotations block**

After the final `kubectl annotate configmap "${CM_NAME}"` call, add:

```bash
REGISTRY_CM_NAME="tools-injector-registry"

echo ""
echo "Creating ConfigMap '${REGISTRY_CM_NAME}' in namespace '${NAMESPACE}'..."

kubectl create configmap "${REGISTRY_CM_NAME}" \
  --from-file=registry.json="${SCRIPT_DIR}/registry.json" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Labeling registry ConfigMap..."
kubectl label configmap "${REGISTRY_CM_NAME}" \
  app.kubernetes.io/part-of=tools-injector \
  -n "${NAMESPACE}" \
  --overwrite
```

- [ ] **Step 4: Update the trailing echo block**

Replace the final echo lines with:
```bash
echo ""
echo "Done."
echo ""
echo "ConfigMaps created in namespace '${NAMESPACE}':"
echo "  inject-tool             — automounted into every workspace at /usr/local/bin/"
echo "  tools-injector-registry — exposes tool registry to Che Dashboard"
echo ""
echo "Usage (from inside a workspace terminal):"
echo "  inject-tool --help"
```

- [ ] **Step 5: Validate bash syntax**

```
bash -n inject-tool/setup.sh
```

Expected: no output.

- [ ] **Step 6: Commit**

```
git add inject-tool/setup.sh
git commit -s -m "feat: create tools-injector-registry ConfigMap in setup.sh"
```

---

### Task 5: Update CLAUDE.md and verify end-to-end

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update inject-tool internals section in CLAUDE.md**

Find and replace in `CLAUDE.md`:
```
The tool registry is a Python dict in `inject-tool.py`:
```
TOOLS = {"tool": {"pattern": "...", "image": "...", "src": "...", "binary": "..."}}
```

Per-tool env vars (`TOOL_ENV[]`) and setup commands (`TOOL_SETUP[]`) are also hardcoded in the same file.
```

Replace with:
```
The tool registry is `inject-tool/registry.json`:
- `registry`, `tag` — default image registry and tag (overridable via `INJECT_TOOL_REGISTRY`/`INJECT_TOOL_TAG` env vars)
- `infrastructure.patch` — RFC 6902 ops for the shared `injected-tools` volume
- `tools.<name>` — per-tool: `description`, `pattern`, `src`, `binary`, `patch` (append-only init container ops), `editor` (volumeMounts, env, postStart)

`inject-tool.py` loads `registry.json` at startup from the same directory (override path with `INJECT_TOOL_REGISTRY_FILE` env var for testing).
```

- [ ] **Step 2: Validate registry.json structure**

```
python3 - <<'PYEOF'
import json

with open('inject-tool/registry.json') as f:
    reg = json.load(f)

expected_tools = {'opencode', 'goose', 'claude-code', 'kilocode', 'gemini-cli', 'tmux', 'python3'}
assert set(reg['tools'].keys()) == expected_tools

for name, t in reg['tools'].items():
    for op in t['patch']:
        assert op['op'] == 'add' and op['path'].endswith('/-'), f"{name}: bad patch op"
    assert isinstance(t['editor']['env'], list)
    assert isinstance(t['editor']['volumeMounts'], list)
    assert isinstance(t['editor'].get('postStart', ''), str)

assert reg['tools']['claude-code']['editor']['env'][0]['name'] == 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC'
assert reg['tools']['gemini-cli']['editor']['postStart'] \!= ''
print("OK — registry.json structure valid")
PYEOF
```

Expected: `OK — registry.json structure valid`

- [ ] **Step 3: Verify no old constants remain in inject-tool.py**

```
grep -c "TOOLS\b\|TOOL_ENV\b\|TOOL_SETUP\b" inject-tool/inject-tool.py
```

Expected: `0`

- [ ] **Step 4: Verify inject-tool.py loads and env var override works**

```
python3 - <<'PYEOF'
import os, sys, types

os.environ['INJECT_TOOL_REGISTRY_FILE'] = 'inject-tool/registry.json'
os.environ['INJECT_TOOL_REGISTRY'] = 'quay.io/myorg'
os.environ['INJECT_TOOL_TAG'] = 'dev'

src = open('inject-tool/inject-tool.py').read()
# Run only up to the Kubernetes helpers (no network calls)
exec_src = src[:src.index('\n# ============\n# Kubernetes API')]
ns = {'__file__': 'inject-tool/inject-tool.py'}
exec(exec_src, ns)

img = ns['tool_image']('opencode')
assert img == 'quay.io/myorg/tools-injector/opencode:dev', f"Got: {img}"
assert 'claude-code' in ns['REGISTRY_DATA']['tools']
print("OK — env var overrides and registry loading work")
PYEOF
```

Expected: `OK — env var overrides and registry loading work`

- [ ] **Step 5: Commit**

```
git add CLAUDE.md
git commit -s -m "docs: update CLAUDE.md to reflect registry.json as source of truth"
```
