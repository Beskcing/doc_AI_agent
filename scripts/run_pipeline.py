"""文档排版智能体 CLI 入口

用法:
    python -m scripts.run_pipeline --input doc.pdf --output output.docx
    python -m scripts.run_pipeline --input doc.md --standard "GB/T 1.1" --provider glm
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.api.services.pipeline_service import PipelineService
from src.api.services.service_deps import ServiceDeps
from src.config import AppConfig
from src.db.database import init_db
from src.db.session import get_db_session
from src.utils.file_utils import ensure_dir, write_text_file
from src.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="企业级国标文档排版智能体",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m scripts.run_pipeline --input doc.pdf --output output.docx
  python -m scripts.run_pipeline --input doc.md --standard "GB/T 1.1" --provider glm
  python -m scripts.run_pipeline --input doc.md --output-json style.json --skip-render
        """,
    )

    parser.add_argument("--input", "-i", required=True, help="输入文件路径（PDF 或 Markdown）")
    parser.add_argument("--output", "-o", default="data/output/output.docx", help="输出 Word 文件路径")
    parser.add_argument("--standard", "-s", default="GB/T 1.1", help="目标标准编号，如 GB/T 1.1")
    parser.add_argument("--provider", "-p", default=None, help="LLM Provider (qwen / glm)")
    parser.add_argument("--config", "-c", default=None, help="配置文件路径")
    parser.add_argument("--output-json", default=None, help="额外输出 style_config JSON 文件")
    parser.add_argument("--output-markdown", default=None, help="额外输出清洗后 Markdown 文件")
    parser.add_argument("--skip-render", action="store_true", help="跳过渲染阶段（仅输出 JSON 和 Markdown）")
    parser.add_argument("--no-rag", action="store_true", help="禁用 RAG 知识库")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    args = parser.parse_args()

    setup_logging()

    logger.info("=" * 60)
    logger.info("  企业级国标文档排版智能体 v0.1.0")
    logger.info("=" * 60)

    start_time = time.time()

    # 加载配置
    config = AppConfig.load(args.config)
    if args.provider:
        config.llm.default_provider = args.provider

    # 校验输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("输入文件不存在: %s", input_path)
        sys.exit(1)

    logger.info("输入文件: %s", input_path)
    logger.info("目标标准: %s", args.standard or "(自动检测)")
    logger.info("LLM Provider: %s", config.llm.default_provider)

    # 初始化数据库
    init_db()

    # 使用 ServiceDeps + PipelineService（与 API 路径一致）
    deps = ServiceDeps(config, enable_rag=not args.no_rag)
    if not args.no_rag:
        logger.info("RAG 知识库将按需加载")
    else:
        logger.info("已禁用 RAG 知识库")

    pipeline = PipelineService(deps, update_status=lambda *a, **kw: None)

    # 创建 DB 任务记录
    task_id = str(uuid.uuid4())
    with get_db_session() as db:
        from src.db.crud import TaskCRUD

        TaskCRUD.create(
            db,
            id=task_id,
            upload_id=task_id,
            filename=input_path.name,
            standard=args.standard or "",
            status="processing",
            progress=0,
            current_step="init",
            config={"cli_mode": True, "file_path": str(input_path)},
        )

    logger.info("-" * 60)
    logger.info("开始执行工作流 (task_id=%s)...", task_id)

    error_msg = None
    cleaned_md = ""
    styled_path = None
    style_config = {}

    try:
        cleaned_md, styled_path, _mineru_docx, style_config = pipeline.process_task(
            task_id=task_id,
            file_path=str(input_path),
            target_standard=args.standard,
            template_id=None,
            config={"cli_mode": True},
        )
        # 更新任务状态为完成
        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            TaskCRUD.update_status(
                db,
                task_id,
                status="completed",
                progress=100,
                current_step="done",
                error_message=None,
            )
            from datetime import datetime as _dt

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.completed_at = _dt.now()
                task_db.result_path = styled_path
                db.commit()
        logger.info("工作流执行成功！")
    except Exception as e:
        error_msg = str(e)
        logger.error("工作流错误: %s", e)
        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            TaskCRUD.update_status(
                db,
                task_id,
                status="failed",
                error_message=error_msg,
            )

    # 输出结果
    elapsed = time.time() - start_time
    logger.info("-" * 60)

    if styled_path and not args.skip_render:
        logger.info("输出文件: %s", styled_path)
        # 复制到用户指定的输出路径
        if args.output and args.output != "data/output/output.docx":
            import shutil

            ensure_dir(Path(args.output).parent)
            shutil.copy2(styled_path, args.output)
            logger.info("已复制到: %s", args.output)

    # 额外输出
    if args.output_json and style_config:
        json_path = write_text_file(
            args.output_json,
            json.dumps(style_config, ensure_ascii=False, indent=2),
        )
        logger.info("样式配置已保存: %s", json_path)

    if args.output_markdown and cleaned_md:
        md_path = write_text_file(args.output_markdown, cleaned_md)
        logger.info("清洗后 Markdown 已保存: %s", md_path)

    logger.info("=" * 60)
    logger.info("耗时: %.1f 秒", elapsed)
    logger.info("=" * 60)

    # 退出码
    sys.exit(1 if error_msg else 0)


if __name__ == "__main__":
    main()
