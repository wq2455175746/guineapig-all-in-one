"""
DAG 验证器 — 确保生成的 DAG 是可执行、无循环、能力可用的。

验证规则：
1. 步骤 ID 唯一性
2. 依赖的 step_id 必须存在（无悬挂引用）
3. 无循环依赖（拓扑排序检测）
4. 引用的能力必须在当前能力清单中可用
5. 参数引用校验（{{step_id.output_key}} / {{output_key}}）— step_id 存在、
   output_key 已声明、引用的步骤在 depends_on 中（保证执行顺序）
"""

import re

from app.core.log import logger
from ..models import CapabilityInventory, DAGDefinition, DAGStep

# 完整引用 {{step_id.output_key}}
FULL_REF_PATTERN = re.compile(r"\{\{(\w+)\.(\w+)\}\}")
# 裸引用 {{output_key}}
BARE_REF_PATTERN = re.compile(r"\{\{(\w+)\}\}")


class DAGValidator:
    """DAG 验证器"""

    @classmethod
    def validate(
        cls,
        dag: DAGDefinition,
        inventory: CapabilityInventory | None = None,
    ) -> tuple[bool, list[str]]:
        """
        验证 DAG 是否可执行。

        Args:
            dag: 待验证的 DAG
            inventory: 当前能力清单（用于检查能力可用性）

        Returns:
            (是否通过, 错误信息列表)
        """
        errors: list[str] = []

        if not dag.steps:
            errors.append("DAG 没有步骤")
            return False, errors

        cls._check_step_id_uniqueness(dag, errors)
        cls._check_dangling_references(dag, errors)
        cls._check_cycle(dag, errors)
        cls._check_param_references(dag, errors)

        if inventory:
            cls._normalize_capabilities(dag, inventory)
            cls._check_capability_availability(dag, inventory, errors)

        if errors:
            return False, errors
        return True, []

    @classmethod
    def _normalize_capabilities(
        cls, dag: DAGDefinition, inventory: CapabilityInventory
    ) -> None:
        """将 LLM 可能臆造的能力名归一到真实能力标识符。

        LLM 生成 DAG 时只能看到能力描述（如 ``MCP [amap]``），看不到确切标识符
        ``mcp_amap``，因此常拼出 ``amap_mcp`` / ``mcp_amap_maps_weather`` 之类的变体。
        这里对每个步骤做归一化：命中清单中任意真实能力即改写 step.capability，
        避免校验拒绝导致整个 DAG 被丢弃。
        """
        real_names = [cap.name for cap in inventory.capabilities if cap.enabled]
        real_set = set(real_names)
        for step in dag.steps:
            cap_name = step.capability
            if cap_name in real_set:
                continue
            canonical = cls._resolve_capability(cap_name, real_names)
            if canonical:
                step.capability = canonical
                logger.info(
                    f"[Validator] 能力名归一化: '{cap_name}' -> '{canonical}'"
                )

    @classmethod
    def _resolve_capability(cls, cap_name: str, real_names: list[str]) -> str:
        """把 LLM 的猜测名映射到真实能力名；无法确定时返回空串。"""
        # 1. 精确（大小写不敏感）
        lowered = cap_name.lower()
        for name in real_names:
            if name.lower() == lowered:
                return name
        # 2. 令牌重叠：mcp_amap 与 amap_mcp / mcp_amap_maps_weather 共享 {amap, mcp}
        cap_tokens = {t for t in lowered.replace("-", "_").split("_") if t}
        best, best_score = "", -1
        for name in real_names:
            name_tokens = {t for t in name.lower().replace("-", "_").split("_") if t}
            if not name_tokens:
                continue
            overlap = len(cap_tokens & name_tokens)
            # 3. 或子串包含（server 名出现在猜测名中）
            if any(t in lowered for t in name_tokens):
                score = overlap + 1
            else:
                score = overlap
            if score > best_score:
                best, best_score = name, score
        return best if best_score > 0 else ""

    @classmethod
    def _check_step_id_uniqueness(
        cls, dag: DAGDefinition, errors: list[str]
    ) -> None:
        """检查步骤 ID 是否唯一"""
        seen: dict[str, int] = {}
        for step in dag.steps:
            seen[step.step_id] = seen.get(step.step_id, 0) + 1

        duplicates = [sid for sid, count in seen.items() if count > 1]
        if duplicates:
            errors.append(f"重复的 step_id: {', '.join(duplicates)}")

    @classmethod
    def _check_dangling_references(
        cls, dag: DAGDefinition, errors: list[str]
    ) -> None:
        """检查 depends_on 是否引用不存在的 step_id"""
        all_ids = {step.step_id for step in dag.steps}

        for step in dag.steps:
            for dep_id in step.depends_on:
                if dep_id not in all_ids:
                    errors.append(
                        f"步骤 '{step.step_id}' 依赖不存在的步骤 '{dep_id}'"
                    )

    @classmethod
    def _check_cycle(cls, dag: DAGDefinition, errors: list[str]) -> None:
        """使用 Kahn 拓扑排序检测循环依赖"""
        # 构建反向邻接表: A→B 表示 A depends_on B, B 必须在 A 之前执行
        reverse_adj: dict[str, list[str]] = {s.step_id: [] for s in dag.steps}
        for step in dag.steps:
            for dep_id in step.depends_on:
                if dep_id in reverse_adj:
                    reverse_adj[dep_id].append(step.step_id)

        # 入度 = 前置依赖的数量
        indegree: dict[str, int] = {s.step_id: 0 for s in dag.steps}
        for step in dag.steps:
            indegree[step.step_id] = len(step.depends_on)

        # Kahn 拓扑排序: 优先选入度为 0（无前置依赖）的节点
        queue = [sid for sid, deg in indegree.items() if deg == 0]
        sorted_count = 0

        while queue:
            sid = queue.pop(0)
            sorted_count += 1
            # 所有依赖于 sid 的节点入度减 1
            for dependent in reverse_adj.get(sid, []):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)

        if sorted_count != len(dag.steps):
            errors.append("DAG 存在循环依赖，无法拓扑排序")

    @classmethod
    def _check_param_references(
        cls, dag: DAGDefinition, errors: list[str]
    ) -> None:
        """检查步骤参数中的 {{step_id.output_key}} / {{output_key}} 引用：
        - 引用的 step_id 必须存在
        - 裸引用 {{output_key}} 必须由某步骤声明 output_key
        - 被引用的步骤必须在 depends_on 中（保证执行顺序，避免先执行导致占位符无法解析）
        """
        all_ids = {step.step_id for step in dag.steps}
        output_key_to_step: dict[str, str] = {}
        for step in dag.steps:
            if step.output_key and step.output_key not in output_key_to_step:
                output_key_to_step[step.output_key] = step.step_id

        for step in dag.steps:
            dep_set = set(step.depends_on)
            refs = cls._collect_refs(step.params)

            for step_id, key in refs["full"]:
                if step_id not in all_ids:
                    errors.append(
                        f"步骤 '{step.step_id}' 引用了不存在的步骤 "
                        f"'{step_id}' ({{{{{step_id}.{key}}}}})"
                    )
                elif step_id not in dep_set:
                    errors.append(
                        f"步骤 '{step.step_id}' 引用 '{{{{{step_id}.{key}}}}}' "
                        f"但未声明 depends_on=['{step_id}']"
                    )

            for output_key in refs["bare"]:
                producer = output_key_to_step.get(output_key)
                if producer is None:
                    errors.append(
                        f"步骤 '{step.step_id}' 引用了未声明的输出 "
                        f"'{output_key}' ({{{{{output_key}}}}})"
                    )
                elif producer not in dep_set:
                    errors.append(
                        f"步骤 '{step.step_id}' 引用输出 '{{{{{output_key}}}}}'"
                        f"（来自 '{producer}'）但未声明 depends_on=['{producer}']"
                    )

    @classmethod
    def _collect_refs(cls, value) -> dict:
        """递归收集参数中的引用：{"full": [(step_id, key), ...], "bare": [output_key, ...]}"""
        refs: dict = {"full": [], "bare": []}
        if isinstance(value, str):
            for m in FULL_REF_PATTERN.finditer(value):
                refs["full"].append((m.group(1), m.group(2)))
            for m in BARE_REF_PATTERN.finditer(value):
                refs["bare"].append(m.group(1))
        elif isinstance(value, dict):
            for v in value.values():
                sub = cls._collect_refs(v)
                refs["full"].extend(sub["full"])
                refs["bare"].extend(sub["bare"])
        elif isinstance(value, list):
            for v in value:
                sub = cls._collect_refs(v)
                refs["full"].extend(sub["full"])
                refs["bare"].extend(sub["bare"])
        return refs

    @classmethod
    def _check_capability_availability(
        cls,
        dag: DAGDefinition,
        inventory: CapabilityInventory,
        errors: list[str],
    ) -> None:
        """检查 DAG 中引用的能力是否在能力清单中可用"""
        if not inventory.capabilities:
            errors.append("能力清单为空，无法验证 DAG")
            return

        # 构建能力名 → enabled 的映射
        cap_map: dict[str, bool] = {}
        for cap in inventory.capabilities:
            cap_map[cap.name] = cap.enabled
            # 也按 type 匹配
            cap_map[cap.type.value] = cap_map.get(cap.type.value, True) and cap.enabled

        for step in dag.steps:
            cap_name = step.capability
            if cap_name not in cap_map:
                # 尝试匹配能力类型前缀
                matched = False
                for cap in inventory.capabilities:
                    if cap.name.startswith(cap_name) or cap_name.startswith(cap.name):
                        matched = True
                        if not cap.enabled:
                            errors.append(
                                f"步骤 '{step.step_id}' 需要的能力 '{cap_name}' 当前已禁用"
                            )
                        break
                if not matched:
                    errors.append(
                        f"步骤 '{step.step_id}' 需要的能力 '{cap_name}' 不在当前能力清单中"
                    )
