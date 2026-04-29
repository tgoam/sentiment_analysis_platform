"""
Report Engine Flask接口 — thin wrappers delegating to services.report_service.

Phase 2 refactored: business logic extracted to services/report_service.py,
Flask routes are thin wrappers.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from queue import Empty

from flask import Blueprint, request, jsonify, Response, send_file, stream_with_context
from loguru import logger

from services import report_service as svc

# Blueprint — kept for Flask dual-run compatibility
report_bp = Blueprint("report_engine", __name__)


def initialize_report_engine():
    """Initialize ReportEngine (delegates to service). Called from app.py."""
    return svc.initialize_report_engine()


# ── GET /status ────────────────────────────────────────────────────────────

@report_bp.route("/status", methods=["GET"])
def get_status():
    try:
        data = svc.get_status_dict()
        return jsonify({"success": True, **data})
    except Exception as e:
        logger.exception(f"获取Report Engine状态失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── POST /generate ─────────────────────────────────────────────────────────

@report_bp.route("/generate", methods=["POST"])
def generate_report():
    try:
        data = request.get_json() or {}
        if not isinstance(data, dict):
            data = {}
        query = data.get("query", "智能舆情分析报告")
        custom_template = data.get("custom_template", "")

        svc.clear_report_log()

        if not svc.report_agent:
            return jsonify({"success": False, "error": "Report Engine未初始化"}), 500

        engines_status = svc.check_engines_ready()
        if not engines_status["ready"]:
            return jsonify({
                "success": False,
                "error": "输入文件未准备就绪",
                "missing_files": engines_status.get("missing_files", []),
            }), 400

        try:
            task = svc.create_task(query, custom_template)
        except RuntimeError as e:
            return jsonify({"success": False, "error": str(e)}), 400

        svc.start_task_thread(task, query, custom_template)

        return jsonify({
            "success": True,
            "task_id": task.task_id,
            "message": "报告生成已启动",
            "task": task.to_dict(),
            "stream_url": f"/api/report/stream/{task.task_id}",
        })

    except Exception as e:
        logger.exception(f"开始生成报告失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── GET /progress/{task_id} ────────────────────────────────────────────────

@report_bp.route("/progress/<task_id>", methods=["GET"])
def get_progress(task_id: str):
    try:
        task = svc._get_task(task_id)
        if not task:
            return jsonify({
                "success": True,
                "task": {
                    "task_id": task_id,
                    "status": "completed",
                    "progress": 100,
                    "error_message": "",
                    "has_result": True,
                    "report_file_ready": False,
                    "report_file_name": "",
                    "report_file_path": "",
                    "state_file_ready": False,
                    "state_file_path": "",
                },
            })
        return jsonify({"success": True, "task": task.to_dict()})
    except Exception as e:
        logger.exception(f"获取报告生成进度失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── GET /stream/{task_id} (SSE) ────────────────────────────────────────────

@report_bp.route("/stream/<task_id>", methods=["GET"])
def stream_task(task_id: str):
    task = svc._get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": "任务不存在"}), 404

    last_event_header = request.headers.get("Last-Event-ID")
    try:
        last_event_id = int(last_event_header) if last_event_header else None
    except (ValueError, TypeError):
        last_event_id = None

    def client_disconnected() -> bool:
        try:
            env_input = request.environ.get("wsgi.input")
            return bool(getattr(env_input, "closed", False))
        except Exception:
            return False

    def event_generator():
        queue = svc._register_stream(task_id)
        last_data_ts = time.time()
        try:
            history = task.history_since(last_event_id)
            for event in history:
                yield svc._format_sse(event)
                if event.get("type") != "heartbeat":
                    last_data_ts = time.time()

            finished = task.status in svc.STREAM_TERMINAL_STATUSES
            while True:
                if finished:
                    break
                if client_disconnected():
                    logger.info(f"SSE客户端已断开，停止推送: {task_id}")
                    break
                event = None
                try:
                    event = queue.get(timeout=svc.STREAM_HEARTBEAT_INTERVAL)
                except Empty:
                    if task.status in svc.STREAM_TERMINAL_STATUSES:
                        logger.info(f"任务 {task_id} 已结束且无新事件，SSE自动收口")
                        break
                    event = {
                        "id": f"hb-{int(time.time() * 1000)}",
                        "type": "heartbeat",
                        "task_id": task_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "payload": {"status": task.status},
                    }
                if event is None:
                    logger.warning(f"SSE推送获取事件失败（task {task_id}），提前结束")
                    break

                try:
                    yield svc._format_sse(event)
                    if event.get("type") != "heartbeat":
                        last_data_ts = time.time()
                except GeneratorExit:
                    logger.info(f"SSE生成器关闭，停止任务 {task_id} 推送")
                    break
                except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
                    logger.warning(f"SSE连接被客户端中断（task {task_id}）: {exc}")
                    break
                except Exception as exc:
                    event_type = event.get("type") if isinstance(event, dict) else "unknown"
                    logger.exception(f"SSE推送失败（task {task_id}, event {event_type}）: {exc}")
                    break

                if event.get("type") in ("completed", "error", "cancelled"):
                    finished = True
                else:
                    finished = finished or task.status in svc.STREAM_TERMINAL_STATUSES

                if task.status in svc.STREAM_TERMINAL_STATUSES:
                    idle_for = time.time() - last_data_ts
                    if idle_for > svc.STREAM_IDLE_TIMEOUT:
                        logger.info(f"任务 {task_id} 已终态且空闲 {int(idle_for)}s，主动关闭SSE")
                        break
        finally:
            svc._unregister_stream(task_id, queue)

    response = Response(
        stream_with_context(event_generator()),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


# ── GET /result/{task_id} ──────────────────────────────────────────────────

@report_bp.route("/result/<task_id>", methods=["GET"])
def get_result(task_id: str):
    try:
        task = svc._get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        if task.status != "completed":
            return jsonify({"success": False, "error": "报告尚未完成", "task": task.to_dict()}), 400
        return Response(task.html_content, mimetype="text/html")
    except Exception as e:
        logger.exception(f"获取报告生成结果失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── GET /result/{task_id}/json ─────────────────────────────────────────────

@report_bp.route("/result/<task_id>/json", methods=["GET"])
def get_result_json(task_id: str):
    try:
        task = svc._get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        if task.status != "completed":
            return jsonify({"success": False, "error": "报告尚未完成", "task": task.to_dict()}), 400
        return jsonify({"success": True, "task": task.to_dict(), "html_content": task.html_content})
    except Exception as e:
        logger.exception(f"获取报告生成结果失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── GET /download/{task_id} ────────────────────────────────────────────────

@report_bp.route("/download/<task_id>", methods=["GET"])
def download_report(task_id: str):
    try:
        task = svc._get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        if task.status != "completed" or not task.report_file_path:
            return jsonify({"success": False, "error": "报告尚未完成或尚未保存"}), 400
        if not os.path.exists(task.report_file_path):
            return jsonify({"success": False, "error": "报告文件不存在或已被删除"}), 404

        download_name = task.report_file_name or os.path.basename(task.report_file_path)
        return send_file(
            task.report_file_path,
            mimetype="text/html",
            as_attachment=True,
            download_name=download_name,
        )
    except Exception as e:
        logger.exception(f"下载报告失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── POST /cancel/{task_id} ─────────────────────────────────────────────────

@report_bp.route("/cancel/<task_id>", methods=["POST"])
def cancel_task(task_id: str):
    try:
        if svc.cancel_task_by_id(task_id):
            return jsonify({"success": True, "message": "任务已取消"})
        return jsonify({"success": False, "error": "任务不存在或无法取消"}), 404
    except Exception as e:
        logger.exception(f"取消报告生成任务失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── GET /templates ─────────────────────────────────────────────────────────

@report_bp.route("/templates", methods=["GET"])
def get_templates():
    try:
        if not svc.report_agent:
            return jsonify({"success": False, "error": "Report Engine未初始化"}), 500
        data = svc.get_templates_list()
        return jsonify({"success": True, **data})
    except Exception as e:
        logger.exception(f"获取可用模板列表失败: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


# ── GET /log ───────────────────────────────────────────────────────────────

@report_bp.route("/log", methods=["GET"])
def get_report_log():
    try:
        log_lines = svc.get_report_log_lines()
        return jsonify({"success": True, "log_lines": log_lines})
    except PermissionError as e:
        logger.error(f"读取日志权限不足: {str(e)}")
        return jsonify({"success": False, "error": "读取日志权限不足"}), 403
    except UnicodeDecodeError as e:
        logger.error(f"日志文件编码错误: {str(e)}")
        return jsonify({"success": False, "error": "日志文件编码错误"}), 500
    except Exception as e:
        logger.exception(f"读取日志失败: {str(e)}")
        return jsonify({"success": False, "error": f"读取日志失败: {str(e)}"}), 500


# ── POST /log/clear ────────────────────────────────────────────────────────

@report_bp.route("/log/clear", methods=["POST"])
def clear_log():
    try:
        svc.clear_report_log()
        return jsonify({"success": True, "message": "日志已清空"})
    except Exception as e:
        logger.exception(f"清空日志失败: {str(e)}")
        return jsonify({"success": False, "error": f"清空日志失败: {str(e)}"}), 500


# ── GET /export/md/{task_id} ───────────────────────────────────────────────

@report_bp.route("/export/md/<task_id>", methods=["GET"])
def export_markdown(task_id: str):
    try:
        info = svc.export_markdown_for_task(task_id)
        return send_file(
            info["file_path"],
            mimetype="text/markdown",
            as_attachment=True,
            download_name=info["file_name"],
        )
    except LookupError:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.exception(f"导出Markdown失败: {str(e)}")
        return jsonify({"success": False, "error": f"导出Markdown失败: {str(e)}"}), 500


# ── GET /export/pdf/{task_id} ──────────────────────────────────────────────

@report_bp.route("/export/pdf/<task_id>", methods=["GET"])
def export_pdf(task_id: str):
    try:
        from ReportEngine.utils.dependency_check import check_pango_available

        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                "success": False,
                "error": "PDF 导出功能不可用：缺少系统依赖",
                "details": "请安装PDF 导出依赖",
                "help_url": "",
                "system_message": pango_message,
            }), 503

        task = svc.tasks_registry.get(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404

        optimize = request.args.get("optimize", "true").lower() == "true"
        pdf_bytes = svc.export_pdf_for_task(task_id, optimize=optimize)

        with open(task.ir_file_path, "r", encoding="utf-8") as f:
            document_ir = json.load(f)
        topic = document_ir.get("metadata", {}).get("topic", "report")
        pdf_filename = f"report_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{pdf_filename}"',
                "Content-Type": "application/pdf",
            },
        )
    except LookupError:
        return jsonify({"success": False, "error": "任务不存在"}), 404
    except RuntimeError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        logger.exception(f"导出PDF失败: {str(e)}")
        return jsonify({"success": False, "error": f"导出PDF失败: {str(e)}"}), 500


# ── POST /export/pdf-from-ir ───────────────────────────────────────────────

@report_bp.route("/export/pdf-from-ir", methods=["POST"])
def export_pdf_from_ir():
    try:
        from ReportEngine.utils.dependency_check import check_pango_available

        pango_available, pango_message = check_pango_available()
        if not pango_available:
            return jsonify({
                "success": False,
                "error": "PDF 导出功能不可用：缺少系统依赖",
                "details": "请安装PDF 导出依赖",
                "help_url": "",
                "system_message": pango_message,
            }), 503

        data = request.get_json() or {}
        if not isinstance(data, dict) or "document_ir" not in data:
            return jsonify({"success": False, "error": "缺少document_ir参数"}), 400

        document_ir = data["document_ir"]
        optimize = data.get("optimize", True)

        pdf_bytes = svc.export_pdf_from_ir(document_ir, optimize=optimize)

        topic = document_ir.get("metadata", {}).get("topic", "report")
        pdf_filename = f"report_{topic}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{pdf_filename}"',
                "Content-Type": "application/pdf",
            },
        )
    except Exception as e:
        logger.exception(f"从IR导出PDF失败: {str(e)}")
        return jsonify({"success": False, "error": f"导出PDF失败: {str(e)}"}), 500


# ── Error handlers ─────────────────────────────────────────────────────────

@report_bp.errorhandler(404)
def not_found(error):
    logger.exception(f"API端点不存在: {str(error)}")
    return jsonify({"success": False, "error": "API端点不存在"}), 404


@report_bp.errorhandler(500)
def internal_error(error):
    logger.exception(f"服务器内部错误: {str(error)}")
    return jsonify({"success": False, "error": "服务器内部错误"}), 500
