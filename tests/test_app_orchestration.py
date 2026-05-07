"""
测试 app/orchestration/ — LangGraph 顶层协调图
"""

from pathlib import Path
project_root = Path(__file__).parent.parent
import sys
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import MagicMock, patch


class TestOrchestrationState:
    """OrchestrationState TypedDict"""

    def test_minimal_state(self):
        from app.orchestration.graph_state import OrchestrationState
        state: OrchestrationState = {}
        assert state is not None

    def test_state_with_fields(self):
        from app.orchestration.graph_state import OrchestrationState
        state: OrchestrationState = {
            "query": "test report",
            "task_id": "task_123",
            "status": "running",
            "input_ready": True,
        }
        assert state["query"] == "test report"
        assert state["status"] == "running"

    def test_state_all_fields(self):
        from app.orchestration.graph_state import OrchestrationState
        state: OrchestrationState = {
            "query": "q",
            "custom_template": "",
            "task_id": "t1",
            "stream_handler": None,
            "check_result": {"ready": True},
            "input_ready": True,
            "content": {"reports": [], "forum_logs": ""},
            "generation_result": {"html_content": "<h1>Report</h1>"},
            "html_content": "<h1>Report</h1>",
            "report_file_path": "/tmp/report.html",
            "report_file_relative_path": "report.html",
            "report_file_name": "report.html",
            "state_file_path": "/tmp/state.json",
            "ir_file_path": "/tmp/ir.json",
            "status": "completed",
            "error": None,
        }
        assert state["status"] == "completed"


class TestIsInputReady:
    """_is_input_ready 条件边函数"""

    def test_ready(self):
        from app.orchestration.graph import _is_input_ready
        result = _is_input_ready({"input_ready": True})
        assert result == "ready"

    def test_not_ready(self):
        from app.orchestration.graph import _is_input_ready
        result = _is_input_ready({"input_ready": False})
        assert result == "not_ready"

    def test_missing_key(self):
        from app.orchestration.graph import _is_input_ready
        result = _is_input_ready({})
        assert result == "not_ready"


class TestBuildGraph:
    """build_orchestration_graph 函数"""

    def test_graph_compiles(self):
        from app.orchestration.graph import build_orchestration_graph
        mock_agent = MagicMock()
        mock_check = MagicMock(return_value={"ready": True, "missing_files": [], "latest_files": {}})
        graph = build_orchestration_graph(mock_agent, mock_check)
        assert graph is not None

class TestNodeFunctions:
    """Graph 节点函数"""

    def test_check_readiness_ready(self):
        from app.orchestration.graph import build_orchestration_graph
        mock_agent = MagicMock()
        check_result = {"ready": True, "missing_files": [], "latest_files": {"forum": "log.txt"}}
        mock_check = MagicMock(return_value=check_result)
        graph = build_orchestration_graph(mock_agent, mock_check)

        # Invoke the graph
        result = graph.invoke({
            "query": "test",
            "stream_handler": None,
        })
        assert result["status"] == "completed"

    def test_check_readiness_not_ready(self):
        from app.orchestration.graph import build_orchestration_graph
        mock_agent = MagicMock()
        check_result = {"ready": False, "missing_files": ["forum.log"]}
        mock_check = MagicMock(return_value=check_result)
        graph = build_orchestration_graph(mock_agent, mock_check)

        result = graph.invoke({
            "query": "test",
            "stream_handler": None,
        })
        assert result["status"] == "error"
        assert "未准备" in result.get("error", "")

    def test_load_inputs(self):
        from app.orchestration.graph import build_orchestration_graph
        mock_agent = MagicMock()
        mock_agent.load_input_files.return_value = {
            "reports": ["report1.md"], "forum_logs": "forum content"
        }
        mock_check = MagicMock(return_value={"ready": True, "latest_files": {"forum": "log.txt"}})
        graph = build_orchestration_graph(mock_agent, mock_check)

        result = graph.invoke({
            "query": "test",
            "stream_handler": None,
        })
        assert result["content"]["reports"] == ["report1.md"]

    def test_generate_report(self):
        from app.orchestration.graph import build_orchestration_graph
        mock_agent = MagicMock()
        mock_agent.load_input_files.return_value = {"reports": [], "forum_logs": ""}
        mock_agent.generate_report.return_value = {
            "html_content": "<h1>Report</h1>",
            "report_filepath": "/tmp/r.html",
            "report_filename": "r.html",
        }
        mock_check = MagicMock(return_value={"ready": True, "latest_files": {}})
        graph = build_orchestration_graph(mock_agent, mock_check)

        result = graph.invoke({
            "query": "test report",
            "stream_handler": None,
        })
        assert result["status"] == "completed"
        assert "html_content" in result

    def test_stream_handler_called(self):
        from app.orchestration.graph import build_orchestration_graph
        mock_agent = MagicMock()
        mock_agent.load_input_files.return_value = {"reports": [], "forum_logs": ""}
        mock_agent.generate_report.return_value = {"html_content": ""}
        mock_check = MagicMock(return_value={"ready": True, "latest_files": {}})

        events = []
        def handler(evt, data):
            events.append((evt, data))

        graph = build_orchestration_graph(mock_agent, mock_check)
        graph.invoke({
            "query": "test",
            "stream_handler": handler,
        })
        # Should have emitted at least one event
        assert len(events) > 0
