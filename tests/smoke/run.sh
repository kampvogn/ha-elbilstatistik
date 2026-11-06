#!/bin/sh
# Smoke test in a real Home Assistant container: load the integration with a
# config entry, call the lookup service from an automation (one real,
# anonymous API call for a plate that doesn't exist), and fail on errors or
# deprecation warnings from it. Used by CI against the :beta and :dev images
# so a coming release breaking the integration shows up before release day.
#   tests/smoke/run.sh [image tag, default beta]
set -eu
TAG="${1:-beta}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$HERE/../.."
WORK="$(mktemp -d)"
NAME="ha-smoke-$$"
IMAGE="ghcr.io/home-assistant/home-assistant:$TAG"
cleanup() {
    docker rm -f "$NAME" >/dev/null 2>&1 || true
    # Home Assistant writes its files as root; hand them back before deleting.
    docker run --rm --entrypoint chown -v "$WORK:/config" "$IMAGE" -R "$(id -u):$(id -g)" /config >/dev/null 2>&1 || true
    rm -rf "$WORK"
}
trap cleanup EXIT

mkdir -p "$WORK/custom_components" "$WORK/.storage"
cp -r "$ROOT/custom_components/elbilstatistik" "$WORK/custom_components/"
cp "$HERE/configuration.yaml" "$WORK/"
cp "$HERE/core.config_entries" "$WORK/.storage/"
chmod -R a+rwX "$WORK"

docker run -d --name "$NAME" -v "$WORK:/config" "$IMAGE" >/dev/null
docker exec "$NAME" true 2>/dev/null || sleep 5
i=0
until docker logs "$NAME" 2>&1 | grep -q "SMOKE lookup"; do
    i=$((i + 1))
    if [ "$i" -gt 60 ]; then echo "no lookup result after 5 minutes"; break; fi
    sleep 5
done
VERSION="$(docker exec "$NAME" python -c 'import homeassistant.const as c; print(c.__version__)')"
# A clean stop writes the registries (they are saved with a delay).
docker stop -t 60 "$NAME" >/dev/null
LOG="$(docker logs "$NAME" 2>&1)"
echo "Home Assistant $VERSION ($TAG)"

fail=0
check() { if echo "$LOG" | grep -q "$1"; then echo "ok: $2"; else echo "FAIL: $2"; fail=1; fi; }
check "Setup of domain elbilstatistik" "integration set up"
check "SMOKE lookup found=False plate=QQ00000" "lookup service answered from an automation"
if grep -q "sensor.elbilstatistik" "$WORK/.storage/core.entity_registry" 2>/dev/null; then
    echo "ok: sensor registered"; else echo "FAIL: sensor not registered"; fail=1; fi
BAD="$(echo "$LOG" | grep -iE "error|exception|traceback|deprecat" | grep -i "elbilstatistik" || true)"
if [ -n "$BAD" ]; then echo "FAIL: errors or deprecations:"; echo "$BAD"; fail=1; else echo "ok: no errors or deprecation warnings"; fi
[ "$fail" -eq 0 ] || { echo "--- log ---"; echo "$LOG" | tail -60; }
exit "$fail"
