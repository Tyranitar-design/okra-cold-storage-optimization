from src.api.main import _build_agent_response


def test_agent_explains_optuna_warmstart_with_evidence_refs():
    payload = _build_agent_response("解释 Optuna AI warm start")

    assert payload["intent"] == "optuna_warmstart"
    assert payload["policy"]["read_only"] is True
    assert "direct_solver_start" in payload["policy"]["blocked"]
    assert "5.6498x" in payload["reply"]
    assert "4.8364x" in payload["reply"]
    assert "7.18x" in payload["reply"]
    assert "Gurobi" in payload["claim_boundary"]
    assert payload["evidence_refs"]
    assert any(ref["source"] == "/api/v1/experiments/ai-warmstart-report" for ref in payload["evidence_refs"])


def test_agent_keeps_benders_claim_boundary_conservative():
    payload = _build_agent_response("AI-Benders 能不能写显著加速")

    assert payload["intent"] == "benders_boundary"
    assert "不能写成" in payload["reply"]
    assert "cut ranking" in payload["reply"] or "cut 排序" in payload["reply"]
    assert "不能声称通用显著加速" in payload["claim_boundary"]
    assert payload["confidence"] == "high"


def test_agent_next_step_advice_is_evidence_first():
    payload = _build_agent_response("下一步建议")

    assert payload["intent"] == "next_step_advice"
    assert "Agent v2" in payload["reply"]
    assert "复核" in payload["reply"]
    assert payload["evidence_refs"]


def test_agent_live_solve_requires_confirmation_only():
    payload = _build_agent_response("请运行求解")

    assert payload["intent"] == "solve_confirm"
    assert payload["policy"]["read_only"] is True
    assert payload["actions"] == [
        {
            "type": "confirm_solve",
            "label": "确认后打开算法求解过程",
            "route": "/solve",
            "detail": "实时求解会占用本地 Gurobi 资源；我只跳转页面，不直接启动求解。",
        }
    ]
    assert "不会直接启动" in payload["reply"]


def test_agent_export_requires_confirmation_only():
    payload = _build_agent_response("导出论文 markdown")

    assert payload["intent"] == "export_confirm"
    assert payload["policy"]["read_only"] is True
    assert payload["actions"][0]["type"] == "confirm_download"
    assert payload["actions"][0]["route"] == "/export"
    assert "不会直接替您下载" in payload["reply"]
