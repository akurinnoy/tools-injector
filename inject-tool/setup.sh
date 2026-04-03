#!/usr/bin/env bash
# setup.sh <namespace> [--image <service-image>]
#
# Deploys inject-tool-service and the thin client ConfigMap.
set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace> [--image <image>]}"
shift || true

SERVICE_IMAGE="quay.io/akurinnoy/tools-injector/inject-tool-service:next"

while [ $# -gt 0 ]; do
    case "$1" in
        --image) SERVICE_IMAGE="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Deploying RBAC..."
kubectl apply -f "${SCRIPT_DIR}/manifests/rbac.yaml" -n "${NAMESPACE}"

echo "==> Deploying service (image: ${SERVICE_IMAGE})..."
sed "s|IMAGE_PLACEHOLDER|${SERVICE_IMAGE}|g" "${SCRIPT_DIR}/manifests/deployment.yaml" \
    | kubectl apply -f - -n "${NAMESPACE}"

echo "==> Creating inject-tool client ConfigMap..."
CM_NAME="inject-tool"
kubectl create configmap "${CM_NAME}" \
    --from-file=inject-tool="${SCRIPT_DIR}/inject-tool" \
    -n "${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "==> Labeling for DWO automount..."
kubectl label configmap "${CM_NAME}" \
    controller.devfile.io/mount-to-devworkspace=true \
    controller.devfile.io/watch-configmap=true \
    -n "${NAMESPACE}" \
    --overwrite

echo "==> Setting mount annotations..."
kubectl annotate configmap "${CM_NAME}" \
    controller.devfile.io/mount-path=/usr/local/bin \
    controller.devfile.io/mount-as=subpath \
    controller.devfile.io/mount-access-mode=0755 \
    -n "${NAMESPACE}" \
    --overwrite

echo ""
echo "Done."
echo ""
echo "Service deployed to namespace '${NAMESPACE}':"
echo "  inject-tool-service   — HTTP service handling tool injection"
echo "  inject-tool           — thin client automounted into workspaces"
echo ""
echo "Usage (from inside a workspace terminal):"
echo "  inject-tool list"
echo "  inject-tool opencode tmux"
echo "  inject-tool init"
