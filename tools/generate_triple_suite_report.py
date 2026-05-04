#!/usr/bin/env python3
"""Generate a three-suite measured-dimension report for 《我不是演员》, 《废城授印》, and 《荒潮纪元：Steam首发72小时》."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_ACTOR = REPO_ROOT / "scores" / "i-am-not-an-actor"
DEFAULT_FEICHENG = REPO_ROOT / "scores" / "seal-of-the-ruined-city"
DEFAULT_STEAM = REPO_ROOT / "scores" / "era-of-wild-tide-steam-72h"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "reports"
DEFAULT_OUTPUT_JSON = DEFAULT_OUTPUT_DIR / "triple-suite-summary.json"
DEFAULT_OUTPUT_HTML = DEFAULT_OUTPUT_DIR / "triple-suite-report.html"

COLORS = {
    "carbon": "#141412",
    "ink": "#20201c",
    "panel": "#fbfaf6",
    "line": "#d8d4ca",
    "acid": "#b7f05a",
    "signal": "#ff4f3f",
    "cyan": "#2ab7ca",
    "gold": "#f2b84b",
    "violet": "#7c5cff",
}

SUITES = {
    "actor": {
        "label": "《我不是演员》",
        "short": "我不是演员",
        "default_weight": 0.25,
        "required_extra": (),
    },
    "feicheng": {
        "label": "《废城授印》",
        "short": "废城",
        "default_weight": 0.30,
        "required_extra": (),
    },
    "steam": {
        "label": "《荒潮纪元：Steam首发72小时》",
        "short": "荒潮纪元",
        "default_weight": 0.45,
        "required_extra": (
            "round_scores",
            "score_cap",
            "data_trust_audit",
            "certainty_audit",
            "deadline_execution_audit",
            "access_boundary_audit",
        ),
    },
}

SUITE_SHORT_LABELS = {
    "actor": "我不是演员",
    "feicheng": "《废城授印》",
    "steam": "荒潮纪元",
}

PRACTICAL_TOP_SUMMARY = (
    "实用分工上，Opus4.6 可以作为三题组里的主审和终局合成模型，用来处理高压、多约束、"
    "需要证据边界和执行取舍同时成立的任务；GLM5.1 与 ChatGPT 更适合做稳定的执行方案、"
    "材料整理和二审校对；Kimi、DeepSeek 更适合中文长文、复杂叙事、证据复盘和常压材料判断，"
    "但不宜单独承担经营生死线或不可退让红线的最终拍板；MiMo、Gemini 可用于叙事表达、"
    "候选比较和方案草案，但需要外部守住证据边界、红线和公开承诺；MiniMax、豆包更适合作为"
    "结构化初稿、责任清单和行动表生成器，不应独立负责预算审批、平台合规、对外承诺或高压终局决策。"
)

PRACTICAL_PROFILES = {
    "opus46": {
        "best_at": "高风险综合判断、复杂证据审读、压力下终局拍板、跨部门危机指挥。",
        "assign_to": "主审、最终汇总、关键结论复核、临门经营指挥草案。",
        "avoid": "精细财务模型和高诉讼风险公开文案仍需财务/法务复核。"
    },
    "glm51": {
        "best_at": "结构化执行计划、多候选材料审读、高压表达和稳定二审。",
        "assign_to": "行动方案、评审表、指挥令初稿、红线判断的第二意见。",
        "avoid": "严格事实审计和低置信来源分层需要额外校验，别让它单独定性。"
    },
    "chatgpt": {
        "best_at": "均衡型材料整理、故事内证据动作、运营指挥和合规收口。",
        "assign_to": "通用主力、跨题组初稿、执行清单、面向人的解释版报告。",
        "avoid": "隐藏暗线穷尽、深财务建模和第三方数据尽调不宜只靠它。"
    },
    "deepseek": {
        "best_at": "中文长上下文叙事、常压材料比较、证据备注和抗误导续写。",
        "assign_to": "叙事诊断、材料摘要、候选排序草案、复杂中文文本审读。",
        "avoid": "高压红线守门和经营生死线拍板不稳，Steam 类任务必须有人复核。"
    },
    "kimi": {
        "best_at": "中文叙事理解、隐性主题整合、证据密集复盘和红线材料审阅。",
        "assign_to": "长文阅读、复杂故事/人物关系分析、材料复盘、审计线索整理。",
        "avoid": "对外补偿、服务排期、预算和平台承诺不能让它无人复核发布。"
    },
    "mimo": {
        "best_at": "复杂叙事推理、强表达、责任链草案和中压执行排程。",
        "assign_to": "故事型分析、方案草案、多部门动作表、需要表达张力的材料整理。",
        "avoid": "不可退让红线和权威高压终局拍板；必须外接硬红线审查。"
    },
    "gemini": {
        "best_at": "叙事续写、候选比较、快速生成高密度指挥令和方案框架。",
        "assign_to": "创意/叙事草案、方案备选、材料初筛、对比视角补充。",
        "avoid": "严格证据底稿、对外服务承诺、平台合规和预算终审。"
    },
    "minimax": {
        "best_at": "结构化行动表、责任链、常压材料归纳和临门事项排程。",
        "assign_to": "初稿、清单、会议纪要、已有明确边界下的执行排布。",
        "avoid": "隐藏利益冲突、预算算术、证据归属和高压红线都要人工或强模型复核。"
    },
    "豆包": {
        "best_at": "中文结构化初稿、责任清单、常压候选比较和行动项拆解。",
        "assign_to": "低风险草稿、执行表、材料初筛、需要快速铺开的任务列表。",
        "avoid": "终局拍板、强权威压力下红线判断、商业增长取舍和高精度审计。"
    },
}

NAME_ALIASES = {
    "claudeopus4.6": "opus46",
    "claude-opus-4.6": "opus46",
    "claude opus 4.6": "opus46",
    "deepseekv4pro": "deepseek",
    "deepseek-v4-pro": "deepseek",
    "deepseek v4 pro": "deepseek",
    "glm51": "glm51",
    "glm5.1": "glm51",
    "glm-5.1": "glm51",
    "智谱5.1": "glm51",
    "智谱51": "glm51",
    "智谱": "glm51",
    "kimik2.6": "kimi",
    "kimi-k2.6": "kimi",
    "kimi k2.6": "kimi",
    "mimov2.5pro": "mimo",
    "mimo-v2.5-pro": "mimo",
    "mimo v2.5 pro": "mimo",
    "minimaxm2.7": "minimax",
    "minimax-m2.7": "minimax",
    "minimax m2.7": "minimax",
    "opus4.6": "opus46",
    "opus-4.6": "opus46",
    "opus 4.6": "opus46",
}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def normalize_model_name(name: Any) -> str:
    raw = str(name or "").strip()
    if raw in NAME_ALIASES:
        return NAME_ALIASES[raw]
    compact = re.sub(r"[\s_\-·•]+", "", raw).lower()
    return NAME_ALIASES.get(compact, compact)


def as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} JSON 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path} 根节点不是对象")
    return data


def public_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


def choose_input_paths(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if not source.exists():
        raise FileNotFoundError(f"找不到输入路径: {source}")
    if not source.is_dir():
        raise ValueError(f"输入路径不是 JSON 文件或目录: {source}")
    paths = sorted(
        p for p in source.glob("*.json")
        if "评审输出格式" not in p.name
        and "demo" not in p.name.lower()
        and "汇总" not in p.name
        and "综合" not in p.name
        and "报告" not in p.name
    )
    if not paths:
        raise ValueError(f"{source} 下没有可读取的评分 JSON")
    return paths


def model_items_from_file(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = read_json(path)
    raw_models = data.get("models")
    if isinstance(raw_models, list):
        items = [item for item in raw_models if isinstance(item, dict)]
        meta = {
            "test_id": data.get("test_id"),
            "test_name": data.get("test_name"),
            "test_version": data.get("test_version"),
            "test_date": data.get("test_date"),
            "source": public_path(path),
        }
        return items, meta
    return [data], {
        "test_id": data.get("test_id"),
        "test_name": data.get("test_name"),
        "test_version": data.get("test_version"),
        "test_date": data.get("test_date"),
        "source": public_path(path),
    }


def validate_model(model: dict[str, Any], path: Path, suite_key: str) -> None:
    suite = SUITES[suite_key]
    name = model.get("model_name")
    if not name:
        raise ValueError(f"{path} 中存在缺少 model_name 的模型")
    if "task_axis_scores" in model or "overall_breakdown" in model or "total_score" in model:
        raise ValueError(
            f"{path} / {name} 使用了不兼容评分结构；请按当前 {suite['label']} 评分标准重新评审"
        )
    dims = model.get("measured_dimensions")
    if not isinstance(dims, dict) or not dims:
        raise ValueError(f"{path} / {name} 缺少 measured_dimensions")
    score = model.get("question_score")
    if not isinstance(score, dict) or as_float(score.get("score")) is None:
        raise ValueError(f"{path} / {name} 缺少 question_score.score")
    for key, dim in dims.items():
        if not isinstance(dim, dict):
            raise ValueError(f"{path} / {name} measured_dimensions.{key} 不是对象")
        if as_float(dim.get("score")) is None:
            raise ValueError(f"{path} / {name} measured_dimensions.{key}.score 缺失或非数字")
        if not dim.get("label"):
            raise ValueError(f"{path} / {name} measured_dimensions.{key}.label 缺失")
    for key in suite["required_extra"]:
        if key not in model:
            raise ValueError(f"{path} / {name} 缺少 Steam 必需字段 {key}")


def collect_models(source: Path, suite_key: str) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    models: dict[str, dict[str, Any]] = {}
    metas: list[dict[str, Any]] = []
    for path in choose_input_paths(source):
        items, meta = model_items_from_file(path)
        metas.append(meta)
        for model in items:
            validate_model(model, path, suite_key)
            key = normalize_model_name(model.get("model_name"))
            models[key] = model
    if not models:
        raise ValueError(f"{SUITES[suite_key]['label']} 没有可用新版模型评分")
    return models, metas


def question_score(model: dict[str, Any] | None) -> float | None:
    if not model:
        return None
    score = model.get("question_score")
    if not isinstance(score, dict):
        return None
    value = as_float(score.get("score"))
    return round(value, 1) if value is not None else None


def rank_scores(scores: dict[str, float | None]) -> dict[str, int | None]:
    ranked = sorted(
        ((key, score) for key, score in scores.items() if score is not None),
        key=lambda item: item[1],
        reverse=True,
    )
    ranks: dict[str, int | None] = {key: None for key in scores}
    last_score: float | None = None
    last_rank = 0
    for index, (key, score) in enumerate(ranked, start=1):
        if last_score is None or score != last_score:
            last_rank = index
            last_score = score
        ranks[key] = last_rank
    return ranks


def gates(model: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not model:
        return []
    values = model.get("failure_gates")
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, dict)]


def triggered_gates(model: dict[str, Any] | None) -> list[dict[str, Any]]:
    return [gate for gate in gates(model) if gate.get("triggered") is True]


def gate_level(model: dict[str, Any] | None) -> str:
    levels = {str(gate.get("severity") or "").lower() for gate in triggered_gates(model)}
    if "critical" in levels:
        return "critical"
    if "major" in levels:
        return "major"
    if "medium" in levels:
        return "medium"
    return "none"


def score_class(score: float | None) -> str:
    if score is None:
        return "missing"
    if score >= 90:
        return "excellent"
    if score >= 80:
        return "strong"
    if score >= 70:
        return "mixed"
    return "weak"


def score_color(score: float | None) -> str:
    return {
        "excellent": COLORS["acid"],
        "strong": COLORS["cyan"],
        "mixed": COLORS["gold"],
        "weak": COLORS["signal"],
        "missing": "#a0a0a0",
    }[score_class(score)]


def dim_items(model: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not model:
        return []
    dims = model.get("measured_dimensions")
    if not isinstance(dims, dict):
        return []
    items: list[dict[str, Any]] = []
    for key, value in dims.items():
        if not isinstance(value, dict):
            continue
        score = as_float(value.get("score"))
        items.append(
            {
                "key": key,
                "label": str(value.get("label") or key),
                "score": round(score, 1) if score is not None else None,
                "confidence": str(value.get("confidence") or ""),
                "role": str(value.get("role") or ""),
                "weight": as_float(value.get("weight")),
                "notes": str(value.get("notes") or value.get("evidence") or ""),
            }
        )
    return items


def summary(model: dict[str, Any] | None) -> str:
    if not model:
        return ""
    diag = model.get("diagnostic_summary")
    if isinstance(diag, dict):
        return str(diag.get("summary") or "")
    return ""


def list_from_diag(model: dict[str, Any] | None, key: str) -> list[str]:
    if not model:
        return []
    diag = model.get("diagnostic_summary")
    if not isinstance(diag, dict):
        return []
    values = diag.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if value]


def strings(model: dict[str, Any] | None, key: str) -> list[str]:
    if not model:
        return []
    values = model.get(key)
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for item in values:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            label = item.get("signal") or item.get("mapped_global_capability") or item.get("evidence")
            if label:
                result.append(str(label))
    return result


def audit_strings(model: dict[str, Any] | None, audit_key: str, item_key: str) -> list[str]:
    if not model:
        return []
    audit = model.get(audit_key)
    if not isinstance(audit, dict):
        return []
    values = audit.get(item_key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if value]


def score_cap(model: dict[str, Any] | None) -> dict[str, Any]:
    if not model:
        return {}
    cap = model.get("score_cap")
    return cap if isinstance(cap, dict) else {}


def suite_payload(model: dict[str, Any] | None, score_value: float | None, rank: int | None) -> dict[str, Any]:
    return {
        "score": score_value,
        "rank": rank,
        "summary": summary(model),
        "dimensions": dim_items(model),
        "gates": triggered_gates(model),
        "gate_level": gate_level(model),
        "strengths": list_from_diag(model, "strengths"),
        "risks": list_from_diag(model, "risks"),
        "fit": list_from_diag(model, "fit"),
        "not_fit": list_from_diag(model, "not_fit"),
        "not_tested": strings(model, "not_tested"),
        "indirect_signals": strings(model, "indirect_signals"),
    }


def build_rows(
    suite_models: dict[str, dict[str, dict[str, Any]]],
    weights: dict[str, float],
) -> list[dict[str, Any]]:
    all_keys = sorted(set().union(*(set(models) for models in suite_models.values())))
    suite_scores = {
        suite_key: {key: question_score(model) for key, model in models.items()}
        for suite_key, models in suite_models.items()
    }
    suite_ranks = {suite_key: rank_scores(scores) for suite_key, scores in suite_scores.items()}
    combined_scores: dict[str, float | None] = {}

    for key in all_keys:
        if any(suite_scores[suite_key].get(key) is None for suite_key in suite_models):
            combined_scores[key] = None
            continue
        combined_scores[key] = round(
            sum(suite_scores[suite_key][key] * weights[suite_key] for suite_key in suite_models),
            1,
        )
    combined_ranks = rank_scores(combined_scores)

    rows: list[dict[str, Any]] = []
    for key in all_keys:
        present = [suite_key for suite_key, models in suite_models.items() if key in models]
        missing = [suite_key for suite_key in suite_models if suite_key not in present]
        representative = next((suite_models[suite_key].get(key) for suite_key in suite_models if key in suite_models[suite_key]), {})
        row = {
            "model_name": representative.get("model_name") or key,
            "normalized_name": key,
            "coverage": "complete" if not missing else "partial",
            "present_suites": present,
            "missing_suites": missing,
            "combined_score": combined_scores[key],
            "combined_rank": combined_ranks[key],
        }
        for suite_key in suite_models:
            model = suite_models[suite_key].get(key)
            row[suite_key] = suite_payload(
                model,
                suite_scores[suite_key].get(key),
                suite_ranks[suite_key].get(key),
            )
        steam_model = suite_models["steam"].get(key)
        row["steam"]["score_cap"] = score_cap(steam_model)
        row["steam"]["certainty_overstated"] = audit_strings(
            steam_model, "certainty_audit", "overstated_or_missing_uncertainty"
        )
        row["steam"]["certainty_uncertain"] = audit_strings(steam_model, "certainty_audit", "stated_as_uncertain")
        row["steam"]["verification"] = audit_strings(
            steam_model, "certainty_audit", "verification_owner_and_deadline"
        )
        row["steam"]["data_reject"] = audit_strings(steam_model, "data_trust_audit", "reject_or_isolate")
        row["steam"]["data_caution"] = audit_strings(steam_model, "data_trust_audit", "use_with_caution")
        row["steam"]["deadline_missed"] = audit_strings(steam_model, "deadline_execution_audit", "deferred_or_missed")
        row["steam"]["access_protected"] = audit_strings(
            steam_model, "access_boundary_audit", "protected_internal_data"
        )
        row["steam"]["access_leak"] = audit_strings(steam_model, "access_boundary_audit", "over_shared_or_unbounded")
        row["feicheng"]["final_choice"] = (suite_models["feicheng"].get(key) or {}).get("final_choice")
        row["feicheng"]["songcheng_final_verdict"] = (
            suite_models["feicheng"].get(key) or {}
        ).get("songcheng_final_verdict")
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            row["combined_rank"] is None,
            row["combined_rank"] or 9999,
            str(row["model_name"]).lower(),
        ),
    )


def chips(values: list[str], css_class: str = "chip", limit: int = 6) -> str:
    clipped = [value for value in values if value][:limit]
    if not clipped:
        return '<span class="muted">无</span>'
    return "".join(f'<span class="{css_class}">{esc(value)}</span>' for value in clipped)


def gate_badge(level: str) -> str:
    label = {"critical": "Critical", "major": "Major", "medium": "Medium", "none": "无 gate"}.get(level, level)
    return f'<span class="gate gate-{esc(level)}">{esc(label)}</span>'


def score_badge(score: float | None, rank: int | None = None) -> str:
    if score is None:
        return '<span class="score missing">缺测</span>'
    rank_text = f'<span class="rank">#{rank}</span>' if rank else ""
    return f'<span class="score" style="border-color:{score_color(score)}"><b>{score:.1f}</b>{rank_text}</span>'


def render_dimension_table(title: str, dims: list[dict[str, Any]]) -> str:
    if not dims:
        return f'<div class="empty">{esc(title)}：缺测</div>'
    rows = []
    for dim in dims:
        score = dim["score"]
        weight = dim["weight"]
        rows.append(
            f"""
            <tr>
              <td><b>{esc(dim["label"])}</b><div class="key">{esc(dim["key"])}</div></td>
              <td>{score_badge(score)}</td>
              <td>{esc(dim["confidence"])}</td>
              <td>{"" if weight is None else f"{weight:.0%}"}</td>
              <td>{esc(dim["notes"])}</td>
            </tr>
            """
        )
    return f"""
    <div class="dim-table">
      <h4>{esc(title)}</h4>
      <table>
        <thead><tr><th>维度</th><th>分数</th><th>置信度</th><th>权重</th><th>证据说明</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def suite_label_list(suite_keys: list[str]) -> str:
    return "、".join(SUITE_SHORT_LABELS.get(key, key) for key in suite_keys)


def model_conclusion(row: dict[str, Any]) -> str:
    critical_suites = [
        suite_key
        for suite_key in ("actor", "feicheng", "steam")
        if row[suite_key]["gate_level"] == "critical"
    ]
    gate_levels = [row["actor"]["gate_level"], row["feicheng"]["gate_level"], row["steam"]["gate_level"]]
    major_suites = [
        suite_key
        for suite_key in ("actor", "feicheng", "steam")
        if row[suite_key]["gate_level"] == "major"
    ]
    medium_suites = [
        suite_key
        for suite_key in ("actor", "feicheng", "steam")
        if row[suite_key]["gate_level"] == "medium"
    ]
    if critical_suites:
        parts: list[str] = []
        if "steam" in critical_suites:
            parts.append("Steam 触发 critical gate：不可用于公司/产品生死类经营终局拍板，必须人工复核")
        if "feicheng" in critical_suites:
            parts.append("《废城授印》触发 critical gate：不可用于不可退让红线下的高压终局拍板，必须人工复核")
        if "actor" in critical_suites:
            parts.append("《我不是演员》 触发 critical gate：不可用于高证据边界的叙事/法务判断终局拍板，必须人工复核")
        if major_suites:
            parts.append(f"{suite_label_list(major_suites)} 另有 major gate，需看对应风险")
        if medium_suites:
            parts.append(f"{suite_label_list(medium_suites)} 另有 medium gate，不触发硬封顶")
        return "；".join(parts) + "。"
    if major_suites:
        return f"{suite_label_list(major_suites)} 存在 major gate；当前综合分需要结合对应题组风险阅读，不能只看排名。"
    if medium_suites:
        return f"{suite_label_list(medium_suites)} 存在 medium gate；不触发硬封顶，但对应边界需要复核。"
    if row["combined_score"] is None:
        return "缺少至少一个题组的新评审结果，不能生成三题组综合结论。"
    if row["combined_score"] >= 90:
        return "三题直接测得的证据纪律、压力稳定、任务取舍和现实经营指挥表现很强。"
    if row["combined_score"] >= 80:
        return "三题表现较强，但仍要看 Steam 的确定性校准和平台/权限风险。"
    return "三题表现存在明显不稳定或任务短板，建议先看维度表和触发 gate。"


def practical_profile(row: dict[str, Any]) -> dict[str, str]:
    fallback = {
        "best_at": "当前三题组没有形成稳定专长画像。",
        "assign_to": "只适合作为补充参考，先看单题维度和 gate。",
        "avoid": "不要单独承担高风险终局任务。",
    }
    return PRACTICAL_PROFILES.get(row["normalized_name"], fallback)


def render_suite_block(title: str, suite: dict[str, Any], extra: str = "") -> str:
    return f"""
    <div class="suite">
      <h4>{esc(title)}</h4>
      <div class="suite-meta">{score_badge(suite["score"], suite["rank"])} {gate_badge(suite["gate_level"])}</div>
      <p>{esc(suite["summary"])}</p>
      {extra}
      <div class="subhead">强项</div>{chips(suite["strengths"], "chip good")}
      <div class="subhead">风险</div>{chips(suite["risks"], "chip warn")}
      <div class="subhead">未测</div>{chips(suite["not_tested"], "chip muted-chip")}
    </div>
    """


def render_html(payload: dict[str, Any]) -> str:
    rows = payload["models"]
    complete_rows = [row for row in rows if row["coverage"] == "complete"]
    incomplete_rows = [row for row in rows if row["coverage"] != "complete"]
    generated_at = payload["generated_at"]
    weights = payload["combined_weights"]
    practical_summary = str(payload.get("practical_summary") or PRACTICAL_TOP_SUMMARY)

    leaderboard_rows = []
    for row in complete_rows:
        gate_html = " ".join(gate_badge(row[suite_key]["gate_level"]) for suite_key in ("actor", "feicheng", "steam"))
        leaderboard_rows.append(
            f"""
            <tr>
              <td>{esc(row["combined_rank"])}</td>
              <td><b>{esc(row["model_name"])}</b></td>
              <td>{score_badge(row["combined_score"], row["combined_rank"])}</td>
              <td>{score_badge(row["actor"]["score"], row["actor"]["rank"])}</td>
              <td>{score_badge(row["feicheng"]["score"], row["feicheng"]["rank"])}</td>
              <td>{score_badge(row["steam"]["score"], row["steam"]["rank"])}</td>
              <td>{gate_html}</td>
              <td>{esc(model_conclusion(row))}</td>
            </tr>
            """
        )

    cards = []
    for row in complete_rows:
        profile = practical_profile(row)
        steam_extra = f"""
          <div class="subhead">确定性风险</div>{chips(row["steam"]["certainty_overstated"], "chip warn")}
          <div class="subhead">数据拒采 / 隔离</div>{chips(row["steam"]["data_reject"], "chip neutral")}
          <div class="subhead">临门遗漏</div>{chips(row["steam"]["deadline_missed"], "chip warn")}
          <div class="subhead">权限泄露</div>{chips(row["steam"]["access_leak"], "chip warn")}
        """
        fecheng_extra = (
            f'<div class="choice-line">最终 {esc(row["feicheng"]["final_choice"])} / '
            f'宋澄 {esc(row["feicheng"]["songcheng_final_verdict"])}</div>'
        )
        cards.append(
            f"""
            <section class="panel model-card">
              <div class="card-head">
                <div>
                  <div class="kicker">模型</div>
                  <h3>{esc(row["model_name"])}</h3>
                </div>
                <div class="score-block">{score_badge(row["combined_score"], row["combined_rank"])}</div>
              </div>
              <div class="conclusion">{esc(model_conclusion(row))}</div>
              <div class="practical">
                <div><b>擅长</b>{esc(profile["best_at"])}</div>
                <div><b>分工</b>{esc(profile["assign_to"])}</div>
                <div><b>慎用</b>{esc(profile["avoid"])}</div>
              </div>
              <div class="three-col">
                {render_suite_block("《我不是演员》", row["actor"])}
                {render_suite_block("《废城授印》", row["feicheng"], fecheng_extra)}
                {render_suite_block("《荒潮纪元：Steam首发72小时》", row["steam"], steam_extra)}
              </div>
              {render_dimension_table("《我不是演员》 直接测量维度", row["actor"]["dimensions"])}
              {render_dimension_table("《废城授印》直接测量维度", row["feicheng"]["dimensions"])}
              {render_dimension_table("《荒潮纪元：Steam首发72小时》直接测量维度", row["steam"]["dimensions"])}
            </section>
            """
        )

    incomplete_html = ""
    if incomplete_rows:
        missing = "".join(
            f"<li>{esc(row['model_name'])}: 缺 {esc(', '.join(row['missing_suites']))}</li>"
            for row in incomplete_rows
        )
        incomplete_html = f"""
        <section class="panel">
          <h2>缺测 / 名称未对齐</h2>
          <ul>{missing}</ul>
        </section>
        """

    warnings_html = "".join(f"<li>{esc(warning)}</li>" for warning in payload.get("warnings", [])) or "<li>无</li>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>中文高压复杂任务 Benchmark 报告</title>
<style>
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font-family: Avenir Next, PingFang SC, Noto Sans CJK SC, Microsoft YaHei, sans-serif;
  color: {COLORS['ink']};
  background: #f4f1ea;
}}
.wrap {{ max-width: 1320px; margin: 0 auto; padding: 32px 20px 52px; }}
.panel {{
  background: rgba(251,250,246,.96);
  border: 1px solid {COLORS['line']};
  border-radius: 8px;
  box-shadow: 0 18px 42px rgba(20,20,18,.08);
  padding: 22px;
  margin-bottom: 18px;
}}
.kicker {{ font-size: 12px; letter-spacing: .18em; text-transform: uppercase; color: rgba(32,32,28,.55); }}
h1, h2, h3, h4 {{ margin: 0; color: {COLORS['carbon']}; }}
h1 {{ font-size: 42px; margin-top: 6px; }}
h2 {{ font-size: 24px; margin-bottom: 12px; }}
h3 {{ font-size: 30px; }}
h4 {{ font-size: 18px; margin-bottom: 10px; }}
p {{ line-height: 1.7; color: rgba(32,32,28,.76); }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: {COLORS['carbon']}; color: {COLORS['panel']}; font-weight: 500; }}
td, th {{ text-align: left; vertical-align: top; padding: 10px 12px; border-bottom: 1px solid rgba(216,212,202,.72); font-size: 13px; }}
.score {{
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 5px 8px;
  border: 1px solid #aaa;
  border-radius: 6px;
  background: rgba(255,255,255,.42);
  min-width: 78px;
}}
.score b {{ font-size: 20px; }}
.score.missing {{ color: rgba(32,32,28,.48); }}
.rank {{ color: rgba(32,32,28,.55); font-size: 11px; }}
.gate {{
  display: inline-flex;
  margin: 0 4px 4px 0;
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid {COLORS['line']};
  font-size: 12px;
}}
.gate-critical {{ background: rgba(255,79,63,.13); border-color: rgba(255,79,63,.45); }}
.gate-major {{ background: rgba(242,184,75,.17); border-color: rgba(242,184,75,.55); }}
.gate-medium {{ background: rgba(124,92,255,.10); border-color: rgba(124,92,255,.28); }}
.gate-none {{ background: rgba(183,240,90,.15); border-color: rgba(120,160,40,.25); }}
.meta {{ display:flex; flex-wrap:wrap; gap:16px; margin-top:16px; color:rgba(32,32,28,.68); font-size:13px; }}
.note {{ border-left: 4px solid {COLORS['signal']}; padding: 12px 14px; background: rgba(255,255,255,.42); border-radius: 6px; line-height: 1.7; }}
.card-head {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; margin-bottom: 12px; }}
.three-col {{ display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-top: 16px; }}
.suite {{ border: 1px solid {COLORS['line']}; border-radius: 8px; padding: 14px; background: rgba(255,255,255,.34); }}
.suite-meta {{ margin: 8px 0 10px; }}
.choice-line, .cap {{ font-size: 12px; color: rgba(32,32,28,.64); margin-bottom: 10px; }}
.subhead {{ margin-top: 12px; margin-bottom: 5px; font-size: 11px; letter-spacing: .14em; text-transform: uppercase; color: rgba(32,32,28,.55); }}
.chip {{
  display: inline-block;
  margin: 0 6px 6px 0;
  padding: 5px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.35;
  border: 1px solid {COLORS['line']};
}}
.good {{ background: rgba(183,240,90,.16); }}
.warn {{ background: rgba(255,79,63,.09); }}
.neutral {{ background: rgba(42,183,202,.10); }}
.muted-chip {{ background: rgba(160,160,160,.10); color: rgba(32,32,28,.62); }}
.muted, .empty {{ color: rgba(32,32,28,.48); font-size: 13px; }}
.dim-table {{ margin-top: 18px; }}
.dim-table h4 {{ margin-bottom: 8px; }}
.key {{ color: rgba(32,32,28,.48); font-size: 11px; margin-top: 2px; }}
.conclusion {{ margin: 10px 0; padding: 12px 14px; background: rgba(255,255,255,.45); border-radius: 6px; line-height: 1.7; }}
.practical {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 12px 0 4px;
}}
.practical div {{
  border: 1px solid {COLORS['line']};
  border-radius: 6px;
  background: rgba(255,255,255,.38);
  padding: 10px 12px;
  line-height: 1.55;
  font-size: 13px;
}}
.practical b {{
  display: block;
  margin-bottom: 4px;
  color: rgba(32,32,28,.58);
  font-size: 11px;
  letter-spacing: .12em;
}}
@media (max-width: 980px) {{ .three-col {{ grid-template-columns: 1fr; }} h1 {{ font-size: 34px; }} }}
@media (max-width: 760px) {{ .practical {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header class="panel">
    <div class="kicker">Measured Dimensions Report</div>
    <h1>中文高压复杂任务 Benchmark 报告</h1>
    <div class="meta">
      <span>《我不是演员》权重 {weights['actor']:.0%}</span>
      <span>《废城授印》权重 {weights['feicheng']:.0%}</span>
      <span>《荒潮纪元》权重 {weights['steam']:.0%}</span>
      <span>共同参评模型 {len(complete_rows)}</span>
      <span>生成时间 {esc(generated_at)}</span>
    </div>
    <p class="note">本报告只接受当前评审 JSON。综合分仅表示当前三道题的表现，不代表模型总体能力。《荒潮纪元：Steam首发72小时》权重最高，因为它更直接测公司生死、产品生死、长期利润最大化相关的现实经营指挥、确定性校准、平台风控和权限边界。</p>
  </header>

  <section class="panel">
    <h2>实用分工摘要</h2>
    <p>{esc(practical_summary)}</p>
  </section>

  <section class="panel">
    <h2>当前题组覆盖边界</h2>
    <p>《我不是演员》直接测复杂叙事证据读取、元层推理、证据边界、多轮注意力、高压抗误导和故事内行动。《废城授印》直接测候选结构识别、多候选比较、证据纪律、终局承责和压力稳定。《荒潮纪元：Steam首发72小时》直接测数据口径、经营取舍、确定性校准、跨部门指挥、平台法务风控、权限边界和临门拍板。</p>
    <p>视觉审美、真实系统工程、代码能力、真实法务执业、真实财务审批执行等仍是未测维度，不能由三题综合分外推。</p>
  </section>

  <section class="panel">
    <h2>三题表现入口榜</h2>
    <table>
      <thead><tr><th>排名</th><th>模型</th><th>综合分</th><th>我不是演员</th><th>废城</th><th>荒潮纪元</th><th>Gate</th><th>结论边界</th></tr></thead>
      <tbody>{''.join(leaderboard_rows)}</tbody>
    </table>
  </section>

  {''.join(cards)}
  {incomplete_html}

  <section class="panel">
    <h2>处理警告</h2>
    <ul>{warnings_html}</ul>
  </section>
</div>
</body>
</html>
"""


def normalize_weights(args: argparse.Namespace) -> dict[str, float]:
    weights = {
        "actor": args.actor_weight,
        "feicheng": args.feicheng_weight,
        "steam": args.steam_weight,
    }
    if any(value <= 0 for value in weights.values()):
        raise ValueError("三个题组权重都必须大于 0")
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    weights = normalize_weights(args)
    suite_models = {}
    inputs = {}
    for suite_key, source in (
        ("actor", args.actor),
        ("feicheng", args.feicheng),
        ("steam", args.steam),
    ):
        models, metas = collect_models(Path(source), suite_key)
        suite_models[suite_key] = models
        inputs[suite_key] = metas

    rows = build_rows(suite_models, weights)
    complete_count = sum(1 for row in rows if row["coverage"] == "complete")
    if complete_count == 0:
        raise ValueError("三个题组没有可匹配的共同模型，无法生成三题组报告")

    warnings: list[str] = []
    for row in rows:
        if row["coverage"] != "complete":
            labels = [SUITES[key]["label"] for key in row["missing_suites"]]
            warnings.append(f"{row['model_name']} 缺少 {', '.join(labels)}，未纳入三题组分")

    return {
        "report_id": "triple-suite-measured-dimensions",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "combined_weights": weights,
        "practical_summary": PRACTICAL_TOP_SUMMARY,
        "practical_profiles": PRACTICAL_PROFILES,
        "inputs": inputs,
        "models": rows,
        "warnings": warnings,
    }


def verify_html(output_html: Path, expected_model_count: int) -> None:
    if not output_html.exists():
        raise ValueError(f"未生成 HTML: {output_html}")
    content = output_html.read_text(encoding="utf-8", errors="replace")
    required = ["中文高压复杂任务 Benchmark 报告", "实用分工摘要", "擅长", "分工", "慎用", "荒潮纪元"]
    missing = [item for item in required if item not in content]
    if missing:
        raise ValueError(f"HTML 缺少关键内容: {', '.join(missing)}")
    if str(expected_model_count) not in content:
        raise ValueError(f"HTML 中未找到共同参评模型数 {expected_model_count} 的明显标记")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成《我不是演员》+《废城授印》+《荒潮纪元》三题组综合报告")
    parser.add_argument("--actor", default=str(DEFAULT_ACTOR), help="《我不是演员》评分 JSON 或目录")
    parser.add_argument("--feicheng", default=str(DEFAULT_FEICHENG), help="《废城授印》评分 JSON 或目录")
    parser.add_argument("--steam", default=str(DEFAULT_STEAM), help="《荒潮纪元：Steam首发72小时》评分 JSON 或目录")
    parser.add_argument("--output-json", default=str(DEFAULT_OUTPUT_JSON), help="输出综合 JSON")
    parser.add_argument("--output-html", default=str(DEFAULT_OUTPUT_HTML), help="输出综合 HTML")
    parser.add_argument("--actor-weight", type=float, default=SUITES["actor"]["default_weight"], help="《我不是演员》当前题组权重")
    parser.add_argument(
        "--feicheng-weight",
        type=float,
        default=SUITES["feicheng"]["default_weight"],
        help="《废城授印》当前题组权重",
    )
    parser.add_argument(
        "--steam-weight",
        type=float,
        default=SUITES["steam"]["default_weight"],
        help="《荒潮纪元：Steam首发72小时》当前题组权重",
    )
    args = parser.parse_args()

    try:
        payload = build_payload(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    output_json = Path(args.output_json)
    output_html = Path(args.output_html)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_html.parent.mkdir(parents=True, exist_ok=True)

    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_html.write_text(render_html(payload), encoding="utf-8")

    complete_count = sum(1 for row in payload["models"] if row["coverage"] == "complete")
    try:
        verify_html(output_html, complete_count)
    except ValueError as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    print(f"综合 JSON: {output_json}")
    print(f"HTML 报告: {output_html}")
    print(f"共同参评模型数: {complete_count}")
    if payload["warnings"]:
        print("警告:")
        for warning in payload["warnings"]:
            print(f"- {warning}")
    print("验证: HTML 文件存在且关键区块可检出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
