#!/bin/bash
# ============================================================
# validate_infra.sh — Validate Dockerfile / Helm Chart / docker-compose
# Usage: validate_infra.sh <file_path> [file_path ...]
# ============================================================
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
HAS_ERROR=0

validate_dockerfile() {
    local file="$1"
    python3 -c "
import sys, re
with open('$file') as f:
    lines = f.readlines()
issues = []
valid_instr = {'FROM','RUN','CMD','ENTRYPOINT','COPY','ADD','ENV','ARG','VOLUME','EXPOSE','WORKDIR','USER','LABEL','SHELL','STOPSIGNAL','HEALTHCHECK','ONBUILD','MAINTAINER'}
in_continuation = False
for i, line in enumerate(lines, 1):
    stripped = line.rstrip('\n\r')
    # Skip comments and empties
    if stripped.startswith('#'):
        in_continuation = False
        continue
    if not stripped:
        in_continuation = False
        continue
    # Skip continuation lines (previous line ended with \\)
    if in_continuation:
        in_continuation = stripped.rstrip()[-1:] == '\\\\' if stripped.rstrip() else False
        continue
    # Check for // comment error
    if stripped.lstrip()[:2] == '//':
        issues.append(f'Line {i}: Use \"#\" for comments, not \"//\"')
        continue
    # Parse instruction
    m = re.match(r'^([A-Za-z]+)\s', stripped)
    if m:
        instr = m.group(1).upper()
        if instr not in valid_instr:
            issues.append(f'Line {i}: Unknown instruction \"{m.group(1)}\"')
        # Track continuation
        if stripped.rstrip()[-1:] == '\\\\':
            in_continuation = True
    else:
        # Line starts with instruction continuation (e.g. leading spaces)
        issues.append(f'Line {i}: Unexpected indentation outside instruction')
if not issues:
    if not re.search(r'^FROM\s+\S+', ''.join(lines), re.MULTILINE):
        issues.append('Missing FROM instruction')
if not issues:
    print('  ✓ Syntax OK')
for i in issues:
    print(f'  ⚠️  {i}')
sys.exit(1 if issues else 0)
" 2>&1 || HAS_ERROR=1
}

validate_docker_compose() {
    local file="$1"
    # Try yaml module; fallback to basic checks
    python3 -c "
import sys
try:
    import yaml
    with open('$file') as f:
        yaml.safe_load(f)
    print('  ✓ YAML syntax OK')
    sys.exit(0)
except ModuleNotFoundError:
    # yaml not installed — do basic check: valid YAML quotes, indent
    with open('$file') as f:
        content = f.read()
    if not content.strip():
        print('  ⚠️  Empty file')
        sys.exit(1)
    if 'version:' not in content and 'services:' not in content and 'name:' not in content:
        print('  ⚠️  Does not look like a docker-compose file (no version/services)')
        sys.exit(1)
    print('  ✓ Basic structure OK (yaml module not available for deep check)')
    sys.exit(0)
except yaml.YAMLError as e:
    print(f'  ⚠️  YAML error: {e}')
    sys.exit(1)
except Exception as e:
    print(f'  ⚠️  Error: {e}')
    sys.exit(1)
" 2>&1 || HAS_ERROR=1
}

validate_helm_chart() {
    local chart_dir="$1"
    if [ ! -f "$chart_dir/Chart.yaml" ]; then
        echo "  ⚠️  No Chart.yaml found in $chart_dir"
        HAS_ERROR=1
        return
    fi
    helm lint "$chart_dir" 2>&1 || HAS_ERROR=1
}

# Find Helm chart directory from a file path
find_chart_dir() {
    local file="$1"
    # From template files: deployment/backend/helm/templates/deployment.yaml
    local dir
    dir=$(echo "$file" | sed -n 's|\(.*/helm\)/.*|\1|p')
    if [ -n "$dir" ] && [ -f "$dir/Chart.yaml" ]; then
        echo "$dir"
        return
    fi
    # From values files: deployment/backend/helm/values-dev.yaml
    dir=$(dirname "$file")
    if [ -f "$dir/Chart.yaml" ]; then
        echo "$dir"
        return
    fi
    echo ""
}

# Main
if [ $# -eq 0 ]; then
    echo "Usage: validate_infra.sh <file_path> [...]"
    exit 1
fi

for file in "$@"; do
    basename=$(basename "$file")

    case "$file" in
        *Dockerfile*)
            echo "  [$basename]"
            validate_dockerfile "$file"
            ;;
        *docker-compose*)
            echo "  [$basename]"
            validate_docker_compose "$file"
            ;;
        *deployment/*/helm/*)
            chart_dir=$(find_chart_dir "$file")
            if [ -n "$chart_dir" ]; then
                rel_chart="${chart_dir#$ROOT_DIR/}"
                echo "  [$rel_chart]"
                validate_helm_chart "$chart_dir"
            else
                echo "  ⚠️  Could not locate Helm chart for $file"
                HAS_ERROR=1
            fi
            ;;
        *)
            if echo "$file" | grep -q '/helm/'; then
                chart_dir=$(find_chart_dir "$file")
                if [ -n "$chart_dir" ]; then
                    rel_chart="${chart_dir#$ROOT_DIR/}"
                    echo "  [$rel_chart]"
                    validate_helm_chart "$chart_dir"
                fi
            fi
            ;;
    esac
done

if [ "$HAS_ERROR" -eq 1 ]; then
    echo "❌ Some infra checks failed"
    exit 1
fi
