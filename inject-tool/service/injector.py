"""injector — core patching logic for inject-tool-service."""

import copy
import json
import os
import ssl
import urllib.request

# ============================================================================
# Registry
# ============================================================================
def _registry_path():
    override = os.environ.get("INJECT_TOOL_REGISTRY_FILE")
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "registry.json")


def load_registry():
    path = _registry_path()
    with open(path) as f:
        data = json.load(f)
    for key in ("registry", "tag", "tools"):
        if key not in data:
            raise ValueError(f"registry.json missing required key '{key}'")
    return data


REGISTRY_DATA = load_registry()
_base_registry = os.environ.get("INJECT_TOOL_REGISTRY") or REGISTRY_DATA["registry"]
_base_tag = os.environ.get("INJECT_TOOL_TAG") or REGISTRY_DATA["tag"]


def tool_image(tool):
    return f"{_base_registry}/tools-injector/{tool}:{_base_tag}"


# ============================================================================
# Kubernetes API (in-cluster)
# ============================================================================
CA_CERT = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"


def _get_token():
    with open(SA_TOKEN_PATH) as f:
        return f.read().strip()


def _api_url(namespace, workspace):
    host = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    return (f"https://{host}:{port}/apis/workspace.devfile.io/v1alpha2"
            f"/namespaces/{namespace}/devworkspaces/{workspace}")


def _ssl_context():
    ctx = ssl.create_default_context()
    if os.path.isfile(CA_CERT):
        ctx.load_verify_locations(CA_CERT)
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_workspace(namespace, workspace):
    token = _get_token()
    req = urllib.request.Request(
        _api_url(namespace, workspace),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        return json.loads(resp.read())


def patch_workspace(namespace, workspace, ops):
    token = _get_token()
    data = json.dumps(ops).encode()
    req = urllib.request.Request(
        _api_url(namespace, workspace),
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json-patch+json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        return json.loads(resp.read())


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
    if not mem_str:
        return 0
    if mem_str.endswith("Gi"):
        return int(float(mem_str[:-2]) * 1024)
    if mem_str.endswith("Mi"):
        return int(mem_str[:-2])
    return 0


# ============================================================================
# Custom tool support
# ============================================================================
def build_custom_tool_entry(tool_def):
    for field in ("name", "image", "binaries"):
        if field not in tool_def:
            raise ValueError(f"Custom tool missing required field '{field}': {json.dumps(tool_def)}")
    if not isinstance(tool_def["binaries"], list) or not tool_def["binaries"]:
        raise ValueError(f"Custom tool '{tool_def['name']}': 'binaries' must be a non-empty array")
    for b in tool_def["binaries"]:
        if "src" not in b or "binary" not in b:
            raise ValueError(f"Custom tool '{tool_def['name']}': each binary needs 'src' and 'binary'")

    name = tool_def["name"]
    binaries = tool_def["binaries"]
    mem_limit = tool_def.get("memoryLimit", "128Mi")

    if len(binaries) == 1:
        command = ["/bin/cp"]
        args = [binaries[0]["src"], f"/injected-tools/{binaries[0]['binary']}"]
    else:
        srcs = " ".join(b["src"] for b in binaries)
        command = ["/bin/sh"]
        args = ["-c", f"cp {srcs} /injected-tools/"]

    patch = [{
        "op": "add",
        "path": "/spec/template/components/-",
        "value": {
            "name": f"{name}-injector",
            "container": {
                "image": tool_def["image"],
                "command": command,
                "args": args,
                "memoryLimit": mem_limit,
                "mountSources": False,
                "volumeMounts": [{"name": "injected-tools", "path": "/injected-tools"}],
            },
        },
    }]

    return {
        "description": tool_def.get("description", f"{name} (custom)"),
        "pattern": "init",
        "src": binaries[0]["src"],
        "binary": binaries[0]["binary"],
        "patch": patch,
        "editor": {
            "volumeMounts": [{"name": "injected-tools", "path": "/injected-tools"}],
            "env": tool_def.get("env", []),
            "postStart": tool_def.get("postStart", ""),
        },
        "_binaries": binaries,
    }


# ============================================================================
# Patch construction (from inject-tool.py — unchanged logic)
# ============================================================================
def build_inject_ops(tool, ws, skip_infra=False, tool_entry=None):
    reg_tool = tool_entry if tool_entry else REGISTRY_DATA["tools"][tool]
    pattern = reg_tool["pattern"]
    binary_name = reg_tool["binary"]
    ops = []

    editor = find_editor(ws)
    editor_idx = editor[0] if editor else None
    editor_name = editor[1] if editor else None

    if not skip_infra and find_component_index(ws, "injected-tools") is None:
        ops.extend(copy.deepcopy(REGISTRY_DATA["infrastructure"]["patch"]))

    patch_ops = copy.deepcopy(reg_tool["patch"])
    for op in patch_ops:
        if op.get("op") == "add" and isinstance(op.get("value"), dict):
            container = op["value"].get("container", {})
            if "image" in container and not tool_entry:
                container["image"] = tool_image(tool)
    ops.extend(patch_ops)

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

    commands = ws.get("spec", {}).get("template", {}).get("commands")
    if skip_infra or commands is not None:
        ops.append({"op": "add", "path": "/spec/template/commands/-",
                    "value": {"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}})
    else:
        ops.append({"op": "add", "path": "/spec/template/commands",
                    "value": [{"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}]})

    prestart = get_events(ws).get("preStart")
    if not skip_infra and prestart is None:
        ops.append({"op": "add", "path": "/spec/template/events",
                    "value": {"preStart": [f"install-{tool}"]}})
    else:
        ops.append({"op": "add", "path": "/spec/template/events/preStart/-",
                    "value": f"install-{tool}"})

    if editor_name:
        symlink_cmd_id = f"symlink-{tool}"
        if find_command_index(ws, symlink_cmd_id) is None:
            all_binaries = reg_tool.get("_binaries", [{"src": reg_tool["src"], "binary": binary_name}])
            symlink_parts = []
            for b in all_binaries:
                b_name = b["binary"]
                if pattern == "init":
                    symlink_target = f"/injected-tools/{b_name}"
                else:
                    symlink_target = f"/injected-tools/{tool}/bin/{b_name}"
                symlink_parts.append(f"ln -sf {symlink_target} /injected-tools/bin/{b_name}")

            path_cmd = (
                'grep -q injected-tools /etc/profile.d/injected-tools.sh 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' > /etc/profile.d/injected-tools.sh 2>/dev/null;'
                ' grep -q injected-tools "$HOME/.bashrc" 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' >> "$HOME/.bashrc" 2>/dev/null; true'
            )
            cmdline = (
                f"mkdir -p /injected-tools/bin && "
                f"{' && '.join(symlink_parts)} && "
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


def build_remove_ops(tool, ws, also_removing=None):
    if also_removing is None:
        also_removing = []
    comp_name = f"{tool}-injector"
    ops = []

    comp_idx = find_component_index(ws, comp_name)
    if comp_idx is None:
        raise ValueError(f"{tool} is not injected.")
    ops.append({"op": "remove", "path": f"/spec/template/components/{comp_idx}"})

    cmd_idx = find_command_index(ws, f"install-{tool}")
    if cmd_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{cmd_idx}"})

    event_idx = find_event_index(ws, "preStart", f"install-{tool}")
    if event_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/preStart/{event_idx}"})

    symlink_idx = find_command_index(ws, f"symlink-{tool}")
    if symlink_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{symlink_idx}"})

    post_idx = find_event_index(ws, "postStart", f"symlink-{tool}")
    if post_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/postStart/{post_idx}"})

    removing_names = {f"{r}-injector" for r in also_removing}
    other_injectors = [
        c for c in get_components(ws)
        if c.get("name", "").endswith("-injector")
        and c["name"] != comp_name
        and c["name"] not in removing_names
    ]

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
    if op.get("op") != "remove":
        return (-1, "")
    parts = op.get("path", "").split("/")
    for p in reversed(parts):
        if p.isdigit():
            return (int(p), "/".join(parts[:-1]))
    return (-1, op.get("path", ""))


# ============================================================================
# Handler functions (called by server.py)
# ============================================================================
def handle_inject(namespace, workspace, tools):
    for name in tools:
        if name not in REGISTRY_DATA["tools"]:
            raise ValueError(f"Unknown tool: {name}")

    ws = fetch_workspace(namespace, workspace)

    to_inject = []
    for tool in tools:
        if find_component_index(ws, f"{tool}-injector") is not None:
            continue
        to_inject.append(tool)

    if not to_inject:
        return {"status": "ok", "message": "All requested tools are already injected."}

    all_ops = []
    for i, tool in enumerate(to_inject):
        all_ops.extend(build_inject_ops(tool, ws, skip_infra=(i > 0)))

    bundle_count = sum(1 for t in to_inject if REGISTRY_DATA["tools"][t]["pattern"] == "bundle")
    if bundle_count > 1:
        editor = find_editor(ws)
        if editor:
            editor_idx = editor[0]
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

    patch_workspace(namespace, workspace, all_ops)
    return {"status": "ok", "message": f"Patched {len(to_inject)} tool(s), workspace restarting"}


def handle_remove(namespace, workspace, tools):
    for name in tools:
        if name not in REGISTRY_DATA["tools"]:
            raise ValueError(f"Unknown tool: {name}")

    ws = fetch_workspace(namespace, workspace)

    all_ops = []
    for tool in tools:
        all_ops.extend(build_remove_ops(tool, ws, also_removing=tools))

    all_ops.sort(key=_remove_sort_key, reverse=True)
    patch_workspace(namespace, workspace, all_ops)
    return {"status": "ok", "message": f"Removed {len(tools)} tool(s), workspace restarting"}


def handle_list(namespace, workspace):
    ws = fetch_workspace(namespace, workspace)
    result = []
    for tool in sorted(REGISTRY_DATA["tools"]):
        t = REGISTRY_DATA["tools"][tool]
        injected = find_component_index(ws, f"{tool}-injector") is not None
        result.append({
            "name": tool,
            "description": t["description"],
            "pattern": t["pattern"],
            "injected": injected,
        })
    return {"status": "ok", "tools": result}


def handle_init(namespace, workspace, configs, dry_run=False):
    # Resolve tools from configs
    seen = set()
    resolved = []
    for config in configs:
        project = config.get("project", "unknown")
        tools = config.get("tools", [])
        for item in tools:
            if isinstance(item, str):
                if item in seen:
                    continue
                if item not in REGISTRY_DATA["tools"]:
                    raise ValueError(f"Project '{project}': unknown tool '{item}'")
                seen.add(item)
                resolved.append((item, None))
            elif isinstance(item, dict):
                name = item.get("name")
                if not name:
                    raise ValueError(f"Project '{project}': custom tool missing 'name'")
                if name in seen:
                    continue
                entry = build_custom_tool_entry(item)
                seen.add(name)
                resolved.append((name, entry))
            else:
                raise ValueError(f"Project '{project}': each tool must be a string or object")

    if not resolved:
        return {"status": "ok", "message": "No tools declared in configs."}

    ws = fetch_workspace(namespace, workspace)

    to_inject = []
    for name, entry in resolved:
        if find_component_index(ws, f"{name}-injector") is not None:
            continue
        to_inject.append((name, entry))

    if not to_inject:
        return {"status": "ok", "message": "All declared tools are already injected."}

    if dry_run:
        tool_list = [{"name": n, "type": "custom" if e else "registry"} for n, e in to_inject]
        return {"status": "ok", "message": f"Dry run: would inject {len(to_inject)} tool(s)", "tools": tool_list}

    all_ops = []
    for i, (name, entry) in enumerate(to_inject):
        all_ops.extend(build_inject_ops(name, ws, skip_infra=(i > 0), tool_entry=entry))

    patch_workspace(namespace, workspace, all_ops)
    n_projects = len(configs)
    return {"status": "ok", "message": f"Discovered {len(to_inject)} tool(s) from {n_projects} project(s), workspace restarting"}
