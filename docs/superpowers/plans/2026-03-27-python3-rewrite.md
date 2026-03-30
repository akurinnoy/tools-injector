# inject-tool Python3 Rewrite + Multi-Tool Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Rewrite `inject-tool` from bash to a single-file Python3 script with multi-tool inject/remove support, add a python3 fallback init-container image, and update delivery to use a bash shim + `.py` via ConfigMap.

**Architecture:** `inject-tool` becomes a bash shim that finds python3 (system PATH → `/injected-tools/bin/python3` → error) and exec's `inject-tool.py`. The Python3 script uses only stdlib (`json`, `urllib.request`, `ssl`, `argparse`, `subprocess`, `os`). All JSON manipulation is native Python — no more inline `python3 -c` calls. Multi-tool support merges patch arrays from multiple `build_inject_ops()` calls into one API request.

**Tech Stack:** Python 3 (stdlib only), bash (shim), Docker (python3 image)

**Spec:** `docs/superpowers/specs/2026-03-27-python3-rewrite-design.md`

---

## File Structure

```
inject-tool/
  inject-tool          # NEW: bash shim (~10 lines) — finds python3, exec's inject-tool.py
  inject-tool.py       # NEW: full CLI in Python3 stdlib
  setup.sh             # MODIFY: include both files in ConfigMap
  inject-tool.sh       # DELETE: replaced by inject-tool + inject-tool.py
  README.md            # MODIFY: updated for new architecture

dockerfiles/
  python3/
    Dockerfile         # NEW: python3 init-container image

Makefile               # MODIFY: add python3 to TOOLS list
.github/workflows/
  pr.yml               # MODIFY: add python3 to matrix
  release.yml          # MODIFY: add python3 to matrix
CLAUDE.md              # MODIFY: reflect new architecture
```

---

### Task 1: Create python3 init-container Dockerfile

**Files:**
- Create: `dockerfiles/python3/Dockerfile`

- [x] **Step 1: Create the Dockerfile**

Python3 on Alpine includes the stdlib by default. Extract the binary and stdlib, copy to UBI10.

```dockerfile
# Stage 1: Get python3 + stdlib from Alpine
FROM alpine:3.21 AS builder

RUN apk add --no-cache python3 && \
    # Find the actual python3 binary (not the symlink)
    PYTHON_BIN=$(readlink -f /usr/bin/python3) && \
    cp "$PYTHON_BIN" /usr/local/bin/python3 && \
    chmod +x /usr/local/bin/python3 && \
    # Copy stdlib (needed for json, urllib, ssl, etc.)
    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')") && \
    mkdir -p /usr/local/lib/python${PYTHON_VERSION} && \
    cp -a /usr/lib/python${PYTHON_VERSION}/* /usr/local/lib/python${PYTHON_VERSION}/ && \
    # Copy required shared libraries
    mkdir -p /usr/local/lib && \
    cp /usr/lib/libpython${PYTHON_VERSION}.so* /usr/local/lib/ 2>/dev/null || true

# Stage 2: Minimal runtime image
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /usr/local/bin/python3 /usr/local/bin/python3
COPY --from=builder /usr/local/lib/python* /usr/local/lib/
COPY --from=builder /usr/local/lib/libpython* /usr/lib64/

# Set PYTHONHOME so python3 finds its stdlib
ENV PYTHONHOME=/usr/local

LABEL org.opencontainers.image.description="Python3 runtime for DevWorkspace tool injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/cli-ai-tools"
```

- [x] **Step 2: Test the build locally**

Run:
```bash
docker build -f dockerfiles/python3/Dockerfile -t cli-ai-tools-python3:test .
```
Expected: image builds successfully.

- [x] **Step 3: Verify python3 runs with stdlib modules**

Run:
```bash
docker run --rm cli-ai-tools-python3:test /usr/local/bin/python3 -c "import json, urllib.request, ssl, argparse; print('stdlib OK')"
```
Expected: prints `stdlib OK`.

- [x] **Step 4: Verify the init-container copy pattern works**

Run:
```bash
docker run --rm -v /tmp/tools-test:/tools cli-ai-tools-python3:test /bin/cp /usr/local/bin/python3 /tools/python3
ls -la /tmp/tools-test/python3
rm -rf /tmp/tools-test
```
Expected: binary copied to volume mount.

- [x] **Step 5: Commit**

```bash
git add dockerfiles/python3/Dockerfile
git commit -s -m "feat: add python3 init-container Dockerfile

Alpine-based builder extracts python3 + stdlib into UBI10 minimal.
Used as fallback when workspace containers lack python3."
```

---

### Task 2: Add python3 to Makefile and CI workflows

**Files:**
- Modify: `Makefile:16`
- Modify: `.github/workflows/pr.yml`
- Modify: `.github/workflows/release.yml`

- [x] **Step 1: Add python3 to Makefile TOOLS list**

In `Makefile`, change line 16 from:
```makefile
TOOLS := opencode goose claude-code kilocode gemini-cli
```
to:
```makefile
TOOLS := opencode goose claude-code kilocode gemini-cli python3
```

Note: `tmux` is missing from the current TOOLS list — add it too:
```makefile
TOOLS := opencode goose claude-code kilocode gemini-cli tmux python3
```

- [x] **Step 2: Add python3 to pr.yml matrix**

In `.github/workflows/pr.yml`, add to the matrix list after the tmux entry:
```yaml
          - name: python3
            dockerfile: dockerfiles/python3
```

- [x] **Step 3: Add python3 to release.yml matrix**

In `.github/workflows/release.yml`, add to the matrix list after the tmux entry:
```yaml
          - name: python3
            dockerfile: dockerfiles/python3
```

- [x] **Step 4: Commit**

```bash
git add Makefile .github/workflows/pr.yml .github/workflows/release.yml
git commit -s -m "build: add python3 and tmux to Makefile TOOLS and CI matrices"
```

---

### Task 3: Create the bash shim

**Files:**
- Create: `inject-tool/inject-tool`

- [x] **Step 1: Create the shim**

```bash
#!/usr/bin/env bash
# inject-tool — finds python3 and exec's inject-tool.py
# Delivered via ConfigMap automount to /usr/local/bin/inject-tool

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  exec python3 "${SCRIPT_DIR}/inject-tool.py" "$@"
elif [ -x /injected-tools/bin/python3 ]; then
  exec /injected-tools/bin/python3 "${SCRIPT_DIR}/inject-tool.py" "$@"
else
  echo "ERROR: python3 not found." >&2
  echo "Install python3 or inject it first: inject-tool python3" >&2
  echo "(You'll need to run 'inject-tool python3' from a workspace that has python3.)" >&2
  exit 1
fi
```

- [x] **Step 2: Make executable**

```bash
chmod +x inject-tool/inject-tool
```

- [x] **Step 3: Commit**

```bash
git add inject-tool/inject-tool
git commit -s -m "feat(inject-tool): add bash shim for python3 discovery

Tries python3 on PATH, then /injected-tools/bin/python3, then errors.
Exec's inject-tool.py with the found interpreter."
```

---

### Task 4: Create inject-tool.py — tool registry, CLI parsing, helpers

**Files:**
- Create: `inject-tool/inject-tool.py`

- [x] **Step 1: Create the file with constants, registry, arg parsing, and helpers**

```python
#!/usr/bin/env python3
"""inject-tool — dynamically inject CLI tools into DevWorkspaces."""

import argparse
import json
import os
import ssl
import subprocess
import sys
import urllib.request

# ============================================================================
# Tool registry
# ============================================================================
TOOLS = {
    "opencode":    {"pattern": "init",   "image": "cli-ai-tools-opencode",    "src": "/usr/local/bin/opencode", "binary": "opencode"},
    "goose":       {"pattern": "init",   "image": "cli-ai-tools-goose",       "src": "/usr/local/bin/goose",    "binary": "goose"},
    "claude-code": {"pattern": "init",   "image": "cli-ai-tools-claude-code", "src": "/usr/local/bin/claude",   "binary": "claude"},
    "kilocode":    {"pattern": "bundle", "image": "cli-ai-tools-kilocode",    "src": "/opt/kilocode",           "binary": "kilo"},
    "gemini-cli":  {"pattern": "bundle", "image": "cli-ai-tools-gemini-cli",  "src": "/opt/gemini-cli",         "binary": "gemini"},
    "tmux":        {"pattern": "init",   "image": "cli-ai-tools-tmux",        "src": "/usr/local/bin/tmux",     "binary": "tmux"},
    "python3":     {"pattern": "init",   "image": "cli-ai-tools-python3",     "src": "/usr/local/bin/python3",  "binary": "python3"},
}

TOOL_ENV = {
    "gemini-cli": "GEMINI_CLI_HOME=/tmp/gemini-home",
    "claude-code": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
}

TOOL_SETUP = {
    "gemini-cli": 'mkdir -p /tmp/gemini-home/.gemini && echo \'{"projects":{}}\' > /tmp/gemini-home/.gemini/projects.json',
}

REGISTRY = os.environ.get("INJECT_TOOL_REGISTRY", "quay.io/che-incubator")
TAG = os.environ.get("INJECT_TOOL_TAG", "latest")


# ============================================================================
# Helpers
# ============================================================================
def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(f"==> {msg}")


def tool_image(tool):
    return f"{REGISTRY}/{TOOLS[tool]['image']}:{TAG}"


def validate_tools(tool_names):
    for name in tool_names:
        if name not in TOOLS:
            print(f"Unknown tool: {name}\n", file=sys.stderr)
            print("Available tools:", file=sys.stderr)
            for t in sorted(TOOLS):
                print(f"  {t:<15s} {TOOLS[t]['pattern']}", file=sys.stderr)
            sys.exit(1)


def validate_env():
    for var in ("DEVWORKSPACE_NAMESPACE", "DEVWORKSPACE_NAME"):
        if not os.environ.get(var):
            die(f"{var} not set. Are you running inside a Che workspace?")


# ============================================================================
# CLI parsing
# ============================================================================
def parse_args():
    parser = argparse.ArgumentParser(
        prog="inject-tool",
        description="Dynamically inject CLI tools into DevWorkspaces.",
    )
    sub = parser.add_subparsers(dest="command")

    # inject (default positional)
    inject_p = sub.add_parser("inject", help="Inject one or more tools")
    inject_p.add_argument("tools", nargs="+", metavar="tool")
    inject_p.add_argument("--hot", action="store_true", help="Extract binary without restart (one tool only)")

    # list
    sub.add_parser("list", help="List available tools and status")

    # remove
    remove_p = sub.add_parser("remove", help="Remove one or more injected tools")
    remove_p.add_argument("tools", nargs="+", metavar="tool")
    remove_p.add_argument("--hot", action="store_true", help="Remove hot-injected binary only (one tool only)")

    # Handle bare tool names (no subcommand) — treat as inject
    args = parser.parse_args()
    if args.command is None:
        # Re-parse: treat all positional args as tool names for inject
        # Check if first arg looks like a tool name
        if len(sys.argv) > 1 and sys.argv[1] not in ("-h", "--help"):
            # Inject sys.argv with "inject" prefix
            new_argv = [sys.argv[0], "inject"] + sys.argv[1:]
            args = parser.parse_args(new_argv[1:])
        else:
            parser.print_help()
            sys.exit(0)

    return args


# ============================================================================
# Main
# ============================================================================
def main():
    args = parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "inject":
        validate_tools(args.tools)
        cmd_inject(args.tools, args.hot)
    elif args.command == "remove":
        validate_tools(args.tools)
        cmd_remove(args.tools, args.hot)


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Verify the CLI parsing works locally**

Run:
```bash
cd inject-tool
python3 inject-tool.py --help
python3 inject-tool.py list 2>&1 || true   # will fail on validate_env, that's OK
python3 inject-tool.py opencode 2>&1 || true
python3 inject-tool.py inject opencode goose 2>&1 || true
python3 inject-tool.py remove opencode 2>&1 || true
python3 inject-tool.py badtool 2>&1 || true   # should print "Unknown tool"
```

- [x] **Step 3: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat(inject-tool): add Python3 CLI skeleton with registry and arg parsing"
```

---

### Task 5: Add Kubernetes API helpers

**Files:**
- Modify: `inject-tool/inject-tool.py`

- [x] **Step 1: Add API functions between the helpers and CLI parsing sections**

Insert after `validate_env()` and before `parse_args()`:

```python
# ============================================================================
# Kubernetes API
# ============================================================================
CA_CERT = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
SA_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"


def get_token():
    # Try 1: KUBECONFIG
    kubeconfig = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    if os.path.isfile(kubeconfig):
        with open(kubeconfig) as f:
            for line in f:
                if "token:" in line:
                    token = line.split("token:")[-1].strip()
                    if token:
                        return token

    # Try 2: Service account token
    if os.path.isfile(SA_TOKEN):
        with open(SA_TOKEN) as f:
            return f.read().strip()

    die(f"Could not find auth token. No kubeconfig at {kubeconfig} and no service account token.")


def api_url():
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT")
    if not host or not port:
        die("KUBERNETES_SERVICE_HOST/PORT not set.")
    ns = os.environ["DEVWORKSPACE_NAMESPACE"]
    name = os.environ["DEVWORKSPACE_NAME"]
    return f"https://{host}:{port}/apis/workspace.devfile.io/v1alpha2/namespaces/{ns}/devworkspaces/{name}"


def _ssl_context():
    ctx = ssl.create_default_context()
    if os.path.isfile(CA_CERT):
        ctx.load_verify_locations(CA_CERT)
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_workspace():
    token = get_token()
    req = urllib.request.Request(
        api_url(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context()) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        die(f"Kubernetes API returned HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        die(f"Failed to connect to Kubernetes API: {e.reason}")


def patch_workspace(ops):
    token = get_token()
    data = json.dumps(ops).encode()
    req = urllib.request.Request(
        api_url(),
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json-patch+json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context()) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        die(f"Patch failed with HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        die(f"Failed to connect to Kubernetes API: {e.reason}")
```

- [x] **Step 2: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat(inject-tool): add Kubernetes API helpers (token, fetch, patch)"
```

---

### Task 6: Add workspace JSON helpers

**Files:**
- Modify: `inject-tool/inject-tool.py`

- [x] **Step 1: Add JSON helper functions after the API section**

Insert after `patch_workspace()` and before `parse_args()`:

```python
# ============================================================================
# Workspace JSON helpers
# ============================================================================
def get_components(ws):
    return ws.get("spec", {}).get("template", {}).get("components", [])


def get_commands(ws):
    return ws.get("spec", {}).get("template", {}).get("commands", [])


def get_events(ws):
    return ws.get("spec", {}).get("template", {}).get("events", {})


def find_component_index(ws, name):
    for i, c in enumerate(get_components(ws)):
        if c.get("name") == name:
            return i
    return None


def find_editor(ws):
    """Return (index, name) of the editor component, or None."""
    for i, c in enumerate(get_components(ws)):
        if c.get("container") and not c.get("name", "").endswith("-injector"):
            return i, c["name"]
    return None


def find_command_index(ws, cmd_id):
    for i, c in enumerate(get_commands(ws)):
        if c.get("id") == cmd_id:
            return i
    return None


def find_event_index(ws, event_type, event_id):
    events = get_events(ws).get(event_type, [])
    for i, e in enumerate(events):
        if e == event_id:
            return i
    return None


def parse_memory(mem_str):
    """Parse '2Gi' or '1024Mi' to int (Mi). Returns 0 if unparseable."""
    if not mem_str:
        return 0
    if mem_str.endswith("Gi"):
        return int(float(mem_str[:-2]) * 1024)
    if mem_str.endswith("Mi"):
        return int(mem_str[:-2])
    return 0
```

- [x] **Step 2: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat(inject-tool): add workspace JSON helper functions"
```

---

### Task 7: Implement `cmd_list`

**Files:**
- Modify: `inject-tool/inject-tool.py`

- [x] **Step 1: Add `cmd_list` function before `main()`**

```python
# ============================================================================
# Commands
# ============================================================================
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

- [x] **Step 2: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat(inject-tool): implement list command in Python3"
```

---

### Task 8: Implement `build_inject_ops`

**Files:**
- Modify: `inject-tool/inject-tool.py`

- [x] **Step 1: Add `build_inject_ops` function after `cmd_list()`**

This is the core patch builder. When `skip_infra=True`, it skips infrastructure ops (volume, volume mount, env/commands/events creation, memory bump) and only emits tool-specific append ops.

```python
def build_inject_ops(tool, ws, skip_infra=False):
    t = TOOLS[tool]
    pattern = t["pattern"]
    image = tool_image(tool)
    comp_name = f"{tool}-injector"
    binary_src = t["src"]
    binary_name = t["binary"]
    ops = []

    editor = find_editor(ws)
    editor_idx = editor[0] if editor else None
    editor_name = editor[1] if editor else None

    # 1. Add injected-tools volume if missing
    if not skip_infra and find_component_index(ws, "injected-tools") is None:
        ops.append({"op": "add", "path": "/spec/template/components/-",
                     "value": {"name": "injected-tools", "volume": {"size": "256Mi"}}})

    # 2. Add injector component
    if pattern == "init":
        ops.append({"op": "add", "path": "/spec/template/components/-",
                     "value": {"name": comp_name, "container": {
                         "image": image, "command": ["/bin/cp"],
                         "args": [binary_src, f"/injected-tools/{binary_name}"],
                         "memoryLimit": "128Mi", "mountSources": False,
                         "volumeMounts": [{"name": "injected-tools", "path": "/injected-tools"}]}}})
    else:
        ops.append({"op": "add", "path": "/spec/template/components/-",
                     "value": {"name": comp_name, "container": {
                         "image": image, "command": ["/bin/sh"],
                         "args": ["-c", f"cp -a {binary_src}/. /injected-tools/{tool}/"],
                         "memoryLimit": "256Mi", "mountSources": False,
                         "volumeMounts": [{"name": "injected-tools", "path": "/injected-tools"}]}}})

    # 3. Add volume mount to editor
    if editor_idx is not None and not skip_infra:
        mounts = get_components(ws)[editor_idx].get("container", {}).get("volumeMounts", [])
        has_mount = any(m.get("name") == "injected-tools" for m in mounts)
        if not has_mount:
            if mounts:
                ops.append({"op": "add",
                             "path": f"/spec/template/components/{editor_idx}/container/volumeMounts/-",
                             "value": {"name": "injected-tools", "path": "/injected-tools"}})
            else:
                ops.append({"op": "add",
                             "path": f"/spec/template/components/{editor_idx}/container/volumeMounts",
                             "value": [{"name": "injected-tools", "path": "/injected-tools"}]})
    elif editor_idx is None and not skip_infra:
        print("WARNING: Could not find editor component. You may need to add the volume mount manually.",
              file=sys.stderr)

    # 3b. Add tool-specific env vars
    if editor_idx is not None and tool in TOOL_ENV:
        env_list = get_components(ws)[editor_idx].get("container", {}).get("env")
        env_exists = env_list is not None and len(env_list) > 0
        for i, pair in enumerate(TOOL_ENV[tool].split(";")):
            name, value = pair.split("=", 1)
            if not skip_infra and not env_exists and i == 0:
                ops.append({"op": "add",
                             "path": f"/spec/template/components/{editor_idx}/container/env",
                             "value": [{"name": name, "value": value}]})
                env_exists = True
            else:
                ops.append({"op": "add",
                             "path": f"/spec/template/components/{editor_idx}/container/env/-",
                             "value": {"name": name, "value": value}})

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
                     "value": {"id": f"install-{tool}", "apply": {"component": comp_name}}})
    else:
        ops.append({"op": "add", "path": "/spec/template/commands",
                     "value": [{"id": f"install-{tool}", "apply": {"component": comp_name}}]})

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
            cmdline = f"mkdir -p /injected-tools/bin && ln -sf {symlink_target} /injected-tools/bin/{binary_name} && {path_cmd}"
            if tool in TOOL_SETUP:
                cmdline = f"{TOOL_SETUP[tool]} && {cmdline}"

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

- [x] **Step 2: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat(inject-tool): implement build_inject_ops patch builder"
```

---

### Task 9: Implement `cmd_inject` with multi-tool support

**Files:**
- Modify: `inject-tool/inject-tool.py`

- [x] **Step 1: Add `hot_inject` and `cmd_inject` functions**

Insert after `build_inject_ops()`:

```python
def hot_inject(tool):
    t = TOOLS[tool]
    if t["pattern"] != "init":
        die(f"--hot is only supported for init container tools. Use 'inject-tool {tool}' (without --hot) instead.")
    if subprocess.run(["which", "oc"], capture_output=True).returncode != 0:
        die(f"--hot mode requires the 'oc' CLI. Use 'inject-tool {tool}' (without --hot) for default mode.")

    image = tool_image(tool)
    binary_src = t["src"]
    binary_name = t["binary"]

    os.makedirs("/injected-tools", exist_ok=True)
    info(f"Extracting {binary_name} from {image}...")
    result = subprocess.run(
        ["oc", "image", "extract", image, "--path", f"{binary_src}:/injected-tools/", "--confirm"],
        capture_output=True, text=True)
    if result.returncode != 0:
        die(f"oc image extract failed: {result.stderr}")
    os.chmod(f"/injected-tools/{binary_name}", 0o755)
    info(f"Injected {tool} at /injected-tools/{binary_name} (hot inject — will not survive restart)")


def cmd_inject(tools, hot):
    validate_env()

    if hot:
        if len(tools) > 1:
            die("--hot does not support multiple tools. Inject one tool at a time with --hot.")
        hot_inject(tools[0])
        return

    ws = fetch_workspace()

    # Filter already-injected tools
    to_inject = []
    for tool in tools:
        if find_component_index(ws, f"{tool}-injector") is not None:
            info(f"{tool} is already injected, skipping.")
        else:
            to_inject.append(tool)

    if not to_inject:
        info("All requested tools are already injected.")
        return

    # Build ops: first tool with infra, rest without
    all_ops = []
    for i, tool in enumerate(to_inject):
        all_ops.extend(build_inject_ops(tool, ws, skip_infra=(i > 0)))

    # Fix memory bump for multiple bundle tools
    bundle_count = sum(1 for t in to_inject if TOOLS[t]["pattern"] == "bundle")
    if bundle_count > 1:
        editor = find_editor(ws)
        if editor:
            editor_idx = editor[0]
            # Remove individual bump ops and add correct total
            all_ops = [op for op in all_ops if not op.get("path", "").endswith("/memoryLimit")]
            current_mem = parse_memory(
                get_components(ws)[editor_idx].get("container", {}).get("memoryLimit", ""))
            total_bump = bundle_count * 512
            if current_mem == 0:
                total_mem = 1024 + total_bump
                all_ops.append({"op": "add",
                                "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                                "value": f"{total_mem}Mi"})
            else:
                total_mem = current_mem + total_bump
                all_ops.append({"op": "replace",
                                "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                                "value": f"{total_mem}Mi"})

    tool_names = ", ".join(to_inject)
    info(f"Injecting {tool_names}...")
    patch_workspace(all_ops)
    info(f"Injected {tool_names}. Workspace is restarting...")
```

- [x] **Step 2: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat(inject-tool): implement inject command with multi-tool support"
```

---

### Task 10: Implement `build_remove_ops` and `cmd_remove`

**Files:**
- Modify: `inject-tool/inject-tool.py`

- [x] **Step 1: Add `build_remove_ops` function**

Insert after `cmd_inject()`:

```python
def build_remove_ops(tool, ws, also_removing=None):
    if also_removing is None:
        also_removing = []
    t = TOOLS[tool]
    comp_name = f"{tool}-injector"
    ops = []

    # Find and remove injector component
    comp_idx = find_component_index(ws, comp_name)
    if comp_idx is None:
        die(f"{tool} is not injected.")
    ops.append({"op": "remove", "path": f"/spec/template/components/{comp_idx}"})

    # Remove apply command
    cmd_idx = find_command_index(ws, f"install-{tool}")
    if cmd_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{cmd_idx}"})

    # Remove from preStart events
    event_idx = find_event_index(ws, "preStart", f"install-{tool}")
    if event_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/preStart/{event_idx}"})

    # Remove symlink command
    symlink_idx = find_command_index(ws, f"symlink-{tool}")
    if symlink_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{symlink_idx}"})

    # Remove from postStart events
    post_idx = find_event_index(ws, "postStart", f"symlink-{tool}")
    if post_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/postStart/{post_idx}"})

    # Check if any other injectors remain (excluding tools being removed in this batch)
    removing_names = {f"{r}-injector" for r in also_removing}
    other_injectors = [
        c for c in get_components(ws)
        if c.get("name", "").endswith("-injector")
        and c["name"] != comp_name
        and c["name"] not in removing_names
    ]

    # If no other injectors, remove shared infrastructure
    if not other_injectors:
        vol_idx = find_component_index(ws, "injected-tools")
        if vol_idx is not None:
            ops.append({"op": "remove", "path": f"/spec/template/components/{vol_idx}"})

        editor = find_editor(ws)
        if editor:
            editor_idx = editor[0]
            mounts = get_components(ws)[editor_idx].get("container", {}).get("volumeMounts", [])
            for mi, m in enumerate(mounts):
                if m.get("name") == "injected-tools":
                    ops.append({"op": "remove",
                                "path": f"/spec/template/components/{editor_idx}/container/volumeMounts/{mi}"})
                    break

    return ops


def _remove_sort_key(op):
    """Sort key for remove ops: descending by numeric index in path."""
    if op.get("op") != "remove":
        return (-1, "")
    parts = op.get("path", "").split("/")
    for p in reversed(parts):
        if p.isdigit():
            return (int(p), "/".join(parts[:-1]))
    return (-1, op.get("path", ""))
```

- [x] **Step 2: Add `cmd_remove` function**

```python
def cmd_remove(tools, hot):
    validate_env()

    if hot:
        if len(tools) > 1:
            die("--hot does not support multiple tools.")
        tool = tools[0]
        t = TOOLS[tool]
        if t["pattern"] != "init":
            die("--hot remove is only supported for init container tools.")
        binary_path = f"/injected-tools/{t['binary']}"
        if os.path.exists(binary_path):
            os.remove(binary_path)
        info(f"Removed {binary_path}")
        return

    ws = fetch_workspace()

    all_ops = []
    for tool in tools:
        all_ops.extend(build_remove_ops(tool, ws, also_removing=tools))

    # Sort remove ops by descending index to avoid shifting
    all_ops.sort(key=_remove_sort_key, reverse=True)

    tool_names = ", ".join(tools)
    info(f"Removing {tool_names}...")
    patch_workspace(all_ops)
    info(f"Removed {tool_names}. Workspace is restarting...")
```

- [x] **Step 3: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat(inject-tool): implement remove command with multi-tool support"
```

---

### Task 11: Update setup.sh for two-file ConfigMap

**Files:**
- Modify: `inject-tool/setup.sh`

- [x] **Step 1: Update setup.sh to include both files**

Replace the contents of `inject-tool/setup.sh`:

```bash
#!/usr/bin/env bash
# setup.sh <namespace>
#
# Creates a ConfigMap with the inject-tool shim and Python3 script,
# labeled for DWO automount. After running this, every workspace in the
# namespace will have the tool available at /usr/local/bin/inject-tool.
set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace>}"
CM_NAME="inject-tool"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[[ -f "${SCRIPT_DIR}/inject-tool" ]] || {
  echo "ERROR: inject-tool shim not found in ${SCRIPT_DIR}" >&2
  exit 1
}
[[ -f "${SCRIPT_DIR}/inject-tool.py" ]] || {
  echo "ERROR: inject-tool.py not found in ${SCRIPT_DIR}" >&2
  exit 1
}

echo "Creating ConfigMap '${CM_NAME}' in namespace '${NAMESPACE}'..."

kubectl create configmap "${CM_NAME}" \
  --from-file=inject-tool="${SCRIPT_DIR}/inject-tool" \
  --from-file=inject-tool.py="${SCRIPT_DIR}/inject-tool.py" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Labeling for DWO automount..."
kubectl label configmap "${CM_NAME}" \
  controller.devfile.io/mount-to-devworkspace=true \
  controller.devfile.io/watch-configmap=true \
  -n "${NAMESPACE}" \
  --overwrite

echo "Setting mount annotations..."
kubectl annotate configmap "${CM_NAME}" \
  controller.devfile.io/mount-path=/usr/local/bin \
  controller.devfile.io/mount-as=subpath \
  controller.devfile.io/mount-access-mode=0755 \
  -n "${NAMESPACE}" \
  --overwrite

echo ""
echo "Done. 'inject-tool' will be available at /usr/local/bin/inject-tool"
echo "in every new or restarted workspace in namespace '${NAMESPACE}'."
echo ""
echo "Usage (from inside a workspace terminal):"
echo "  inject-tool --help"
```

- [x] **Step 2: Commit**

```bash
git add inject-tool/setup.sh
git commit -s -m "feat(inject-tool): update setup.sh for two-file ConfigMap delivery"
```

---

### Task 12: Delete old bash script, update docs

**Files:**
- Delete: `inject-tool/inject-tool.sh`
- Modify: `inject-tool/README.md`
- Modify: `CLAUDE.md`

- [x] **Step 1: Delete the old bash script**

```bash
git rm inject-tool/inject-tool.sh
```

- [x] **Step 2: Update inject-tool/README.md**

Replace the contents of `inject-tool/README.md`:

```markdown
# inject-tool

Dynamically inject CLI tools into running DevWorkspaces.

## Setup

Deploy to a namespace (all workspaces in that namespace get `inject-tool`):

\`\`\`bash
./setup.sh <namespace>
\`\`\`

## Usage

From inside a DevWorkspace terminal:

\`\`\`bash
# Inject one or more tools (single restart)
inject-tool opencode
inject-tool claude-code goose tmux

# Inject without restart (one tool only, requires oc CLI)
inject-tool opencode --hot

# List available tools and injection status
inject-tool list

# Remove one or more tools (single restart)
inject-tool remove opencode
inject-tool remove kilocode gemini-cli

# Remove hot-injected binary only (one tool only)
inject-tool remove opencode --hot
\`\`\`

## Available Tools

| Tool | Pattern | Description |
|------|---------|-------------|
| opencode | init | AI coding assistant |
| goose | init | AI developer agent |
| claude-code | init | Anthropic's CLI for Claude |
| tmux | init | Terminal multiplexer |
| python3 | init | Python3 runtime (fallback for inject-tool) |
| kilocode | bundle | AI coding agent |
| gemini-cli | bundle | Google's Gemini CLI |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `INJECT_TOOL_REGISTRY` | `quay.io/che-incubator` | Image registry prefix |
| `INJECT_TOOL_TAG` | `latest` | Image tag |

## Architecture

The tool is delivered as two files via ConfigMap automount:

- **`inject-tool`** — bash shim that finds python3 (system PATH → `/injected-tools/bin/python3` → error) and exec's the Python3 script.
- **`inject-tool.py`** — full CLI written in Python3 stdlib only. Uses `urllib.request` for Kubernetes API, native `json` for patch building.

**Init container tools** (opencode, goose, claude-code, tmux, python3): patches the DevWorkspace CR to add an init container that copies the tool binary to a shared `/injected-tools` volume. A postStart command creates a symlink in `/injected-tools/bin/` and adds it to PATH via `~/.bashrc`.

**Bundle tools** (kilocode, gemini-cli): patches the DevWorkspace CR to add an init container that copies the full Node.js runtime + tool directory to `/injected-tools/<tool>/`. The editor container gets a +512Mi memory bump.

**Hot inject** (`--hot`): extracts the binary from the container image using `oc image extract`. Init-pattern tools only. Not persistent across restarts.
```

- [x] **Step 3: Update CLAUDE.md**

In `CLAUDE.md`, update the "What This Is" section line about inject-tool:
```
2. **inject-tool** (`inject-tool/inject-tool.py`) — Python3 CLI that patches DevWorkspace CRs via Kubernetes API using RFC 6902 JSON Patch. Delivered via ConfigMap as a bash shim + `.py` file.
```

Update the "inject-tool Internals" section:
```
The tool registry is a Python dict in `inject-tool.py`:
\`\`\`
TOOLS = {
    "tool": {"pattern": "...", "image": "...", "src": "...", "binary": "..."},
}
\`\`\`
```

Update the patching flow description:
```
**Patching flow**: validate tools → extract auth token from KUBECONFIG (falls back to service account token) → fetch DevWorkspace CR from Kubernetes API → build inject ops per tool (first with infra, rest skip_infra) → merge into single JSON Patch array → PATCH via API → workspace restarts.

**Multi-tool**: `inject-tool opencode goose tmux` builds patches for each tool, merges into one API call, one restart. `--hot` stays single-tool only.
```

- [x] **Step 4: Commit**

```bash
git add -A
git commit -s -m "feat(inject-tool): complete Python3 rewrite, remove old bash script

Replaces inject-tool.sh (647 lines of bash + inline python3) with:
- inject-tool: bash shim for python3 discovery
- inject-tool.py: full CLI in Python3 stdlib

New features:
- Multi-tool inject: inject-tool opencode goose tmux (single restart)
- Multi-tool remove: inject-tool remove opencode goose (single restart)
- python3 fallback image for containers without python3

setup.sh updated for two-file ConfigMap delivery."
```
