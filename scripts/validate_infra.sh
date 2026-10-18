#!/bin/bash
# ============================================================
# validate_infra.sh — 校验 Dockerfile / Helm Chart / docker-compose
# 用法: validate_infra.sh <file_path> [file_path ...]
#
# 根据传入的文件路径自动判断类型并调用对应校验函数：
#   - *Dockerfile*           -> 校验 Dockerfile 语法与指令合法性
#   - *docker-compose*       -> 校验 compose 文件 YAML 结构
#   - *deployment/*/helm/*   -> 定位 Helm chart 并执行 helm lint
# 任一文件校验失败时，脚本最终以退出码 1 结束。
# ============================================================
set -euo pipefail   # -e 出错即退；-u 未定义变量报错；-o pipefail 管道任一环失败即失败

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"  # 仓库根目录（本脚本位于 scripts/ 下）
HAS_ERROR=0                                    # 累计是否出现过错误（0=无，1=有）

# 校验单个 Dockerfile：用内嵌 Python 做逐行语法检查。
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

# 校验 docker-compose 文件：优先用 PyYAML 做严格解析，缺失 yaml 模块时退化为基本结构检查。
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

# 校验 Helm chart 目录：要求存在 Chart.yaml，并执行 helm lint。
validate_helm_chart() {
    local chart_dir="$1"
    if [ ! -f "$chart_dir/Chart.yaml" ]; then
        echo "  ⚠️  No Chart.yaml found in $chart_dir"
        HAS_ERROR=1
        return
    fi
    helm lint "$chart_dir" 2>&1 || HAS_ERROR=1
}

# 由给定文件路径反推出所在 Helm chart 目录。
find_chart_dir() {
    local file="$1"
    # 情况一：模板文件形如 deployment/backend/helm/templates/deployment.yaml，
    #         截取其 /helm 前缀部分作为 chart 目录。
    local dir
    dir=$(echo "$file" | sed -n 's|\(.*/helm\)/.*|\1|p')
    if [ -n "$dir" ] && [ -f "$dir/Chart.yaml" ]; then
        echo "$dir"
        return
    fi
    # 情况二：values 文件形如 deployment/backend/helm/values-dev.yaml，
    #         其所在目录即为 chart 目录。
    dir=$(dirname "$file")
    if [ -f "$dir/Chart.yaml" ]; then
        echo "$dir"
        return
    fi
    echo ""  # 无法定位
}

# 主流程
if [ $# -eq 0 ]; then
    echo "Usage: validate_infra.sh <file_path> [...]"
    exit 1
fi

# 逐个文件按路径特征分派校验。
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
            # deployment 下的 Helm 相关文件：先找 chart 再 lint。
            chart_dir=$(find_chart_dir "$file")
            if [ -n "$chart_dir" ]; then
                rel_chart="${chart_dir#$ROOT_DIR/}"   # 去掉 ROOT_DIR 前缀，输出相对路径
                echo "  [$rel_chart]"
                validate_helm_chart "$chart_dir"
            else
                echo "  ⚠️  Could not locate Helm chart for $file"
                HAS_ERROR=1
            fi
            ;;
        *)
            # 其它路径：若包含 /helm/ 也尝试按 Helm chart 处理。
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

# 汇总退出码。
if [ "$HAS_ERROR" -eq 1 ]; then
    echo "❌ Some infra checks failed"
    exit 1
fi
