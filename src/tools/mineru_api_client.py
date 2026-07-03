"""MinerU 线上 API 客户端

封装 MinerU 精准解析 API，支持本地文件上传和 URL 两种方式。
工作流：提交任务 → 轮询状态 → 下载 ZIP → 提取 Markdown。

API 文档: https://mineru.net/apiManage/docs
"""

from __future__ import annotations

import io
import time
import zipfile
from enum import Enum
from pathlib import Path
from typing import Any

import requests

from src.utils.file_utils import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)

# MinerU API 基地址
MINERU_API_BASE = "https://mineru.net"


class MinerUTaskState(str, Enum):
    """MinerU 任务状态"""

    PENDING = "pending"          # 排队中
    RUNNING = "running"          # 正在解析
    CONVERTING = "converting"    # 格式转换中
    DONE = "done"                # 完成
    FAILED = "failed"            # 失败
    WAITING_FILE = "waiting-file"  # 等待文件上传（批量上传模式）


class MinerUModelVersion(str, Enum):
    """MinerU 模型版本"""

    PIPELINE = "pipeline"      # 默认管道模型
    VLM = "vlm"                # 视觉语言模型（推荐）
    HTML = "MinerU-HTML"       # HTML 专用


class MinerUAPIClient:
    """MinerU 线上 API 客户端

    封装精准解析 API，支持：
    - 本地文件上传解析（批量上传接口 + PUT 上传）
    - URL 远程文件解析（单文件接口）
    - 任务轮询与结果获取
    - ZIP 结果包下载与 Markdown 提取

    Attributes:
        token: API Token（从 MinerU 平台获取）
        base_url: API 基地址
        timeout: HTTP 请求超时（秒）
        poll_interval: 轮询间隔（秒）
        poll_timeout: 轮询总超时（秒）
    """

    def __init__(
        self,
        token: str,
        base_url: str = MINERU_API_BASE,
        timeout: int = 120,
        poll_interval: int = 5,
        poll_timeout: int = 600,
    ):
        """初始化 API 客户端

        Args:
            token: MinerU API Token
            base_url: API 基地址
            timeout: 单次 HTTP 请求超时
            poll_interval: 轮询任务状态的间隔秒数
            poll_timeout: 轮询总超时秒数
        """
        if not token:
            raise ValueError("MinerU API Token 不能为空")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    @property
    def _headers(self) -> dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }

    # ──────────────────────────────────────────────
    # 1. 单文件 URL 解析
    # ──────────────────────────────────────────────

    def create_task_by_url(
        self,
        file_url: str,
        model_version: str = MinerUModelVersion.VLM,
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: str | None = None,
        extra_formats: list[str] | None = None,
    ) -> str:
        """通过 URL 提交单文件解析任务

        Args:
            file_url: 文件的公开访问 URL
            model_version: 模型版本 (pipeline/vlm/MinerU-HTML)
            is_ocr: 是否启用 OCR
            enable_formula: 是否启用公式识别
            enable_table: 是否启用表格识别
            language: 文档语言
            page_ranges: 页码范围，如 "1-10"
            extra_formats: 额外输出格式，如 ["docx", "html"]

        Returns:
            task_id: 任务 ID

        Raises:
            RuntimeError: API 调用失败
        """
        url = f"{self.base_url}/api/v4/extract/task"
        payload: dict[str, Any] = {
            "url": file_url,
            "model_version": model_version,
            "is_ocr": is_ocr,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
            "language": language,
        }
        if page_ranges:
            payload["page_ranges"] = page_ranges
        if extra_formats:
            payload["extra_formats"] = extra_formats

        logger.info("提交 URL 解析任务: %s (model=%s)", file_url, model_version)
        resp = requests.post(url, headers=self._headers, json=payload, timeout=self.timeout)
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"创建解析任务失败: {data.get('msg', '未知错误')} (code={data.get('code')})")

        task_id = data["data"]["task_id"]
        logger.info("任务已创建: task_id=%s", task_id)
        return task_id

    # ──────────────────────────────────────────────
    # 2. 本地文件上传解析
    # ──────────────────────────────────────────────

    def create_task_by_file(
        self,
        file_path: str | Path,
        model_version: str = MinerUModelVersion.VLM,
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: str | None = None,
        data_id: str | None = None,
        extra_formats: list[str] | None = None,
    ) -> tuple[str, str]:
        """通过本地文件上传提交解析任务

        流程：
        1. 调用批量上传接口获取签名 URL
        2. PUT 上传文件到 OSS
        3. 系统自动提交解析任务

        Args:
            file_path: 本地文件路径
            model_version: 模型版本
            is_ocr: 是否启用 OCR
            enable_formula: 是否启用公式识别
            enable_table: 是否启用表格识别
            language: 文档语言
            page_ranges: 页码范围
            data_id: 自定义数据 ID

        Returns:
            (batch_id, file_name): 批量任务 ID 和文件名

        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: API 调用或上传失败
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        file_name = file_path.name

        # Step 1: 申请上传链接
        url = f"{self.base_url}/api/v4/file-urls/batch"
        file_info: dict[str, Any] = {"name": file_name}
        if data_id:
            file_info["data_id"] = data_id
        if page_ranges:
            file_info["page_ranges"] = page_ranges
        file_info["is_ocr"] = is_ocr

        payload: dict[str, Any] = {
            "files": [file_info],
            "model_version": model_version,
            "enable_formula": enable_formula,
            "enable_table": enable_table,
            "language": language,
        }
        # extra_formats 在请求体顶层，不在 files 数组中
        if extra_formats:
            payload["extra_formats"] = extra_formats

        logger.info("申请上传链接: %s (model=%s)", file_name, model_version)
        resp = requests.post(url, headers=self._headers, json=payload, timeout=self.timeout)
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"申请上传链接失败: {data.get('msg', '未知错误')} (code={data.get('code')})")

        batch_id = data["data"]["batch_id"]
        upload_url = data["data"]["file_urls"][0]

        # Step 2: PUT 上传文件
        logger.info("上传文件到 OSS: %s (%.2f MB)", file_name, file_path.stat().st_size / 1024 / 1024)
        with open(file_path, "rb") as f:
            put_resp = requests.put(upload_url, data=f, timeout=self.timeout)

        if put_resp.status_code not in (200, 201):
            raise RuntimeError(f"文件上传失败: HTTP {put_resp.status_code} - {put_resp.text[:200]}")

        logger.info("文件上传成功: batch_id=%s", batch_id)
        return batch_id, file_name

    # ──────────────────────────────────────────────
    # 3. 查询任务结果
    # ──────────────────────────────────────────────

    def get_task_status(self, task_id: str) -> dict[str, Any]:
        """查询单文件任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态数据，包含 state、full_zip_url 等字段

        Raises:
            RuntimeError: API 调用失败
        """
        url = f"{self.base_url}/api/v4/extract/task/{task_id}"
        resp = requests.get(url, headers=self._headers, timeout=self.timeout)
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"查询任务状态失败: {data.get('msg', '未知错误')} (code={data.get('code')})")

        return data["data"]

    def get_batch_status(self, batch_id: str) -> list[dict[str, Any]]:
        """查询批量任务状态

        Args:
            batch_id: 批量任务 ID

        Returns:
            各文件的状态列表

        Raises:
            RuntimeError: API 调用失败
        """
        url = f"{self.base_url}/api/v4/extract-results/batch/{batch_id}"
        resp = requests.get(url, headers=self._headers, timeout=self.timeout)
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"查询批量任务状态失败: {data.get('msg', '未知错误')} (code={data.get('code')})")

        return data["data"].get("extract_result", [])

    # ──────────────────────────────────────────────
    # 4. 轮询等待完成
    # ──────────────────────────────────────────────

    def wait_for_task(
        self,
        task_id: str,
        on_progress: Any | None = None,
    ) -> str:
        """轮询单文件任务直到完成，返回 ZIP 下载 URL

        Args:
            task_id: 任务 ID
            on_progress: 回调函数 (state, progress_info) -> None

        Returns:
            full_zip_url: 结果 ZIP 包下载地址

        Raises:
            RuntimeError: 任务失败或超时
        """
        logger.info("开始轮询任务: %s", task_id)
        start = time.time()

        while time.time() - start < self.poll_timeout:
            result = self.get_task_status(task_id)
            state = result.get("state", "")

            if state == MinerUTaskState.DONE:
                zip_url = result.get("full_zip_url", "")
                logger.info("任务完成: %s (耗时 %ds)", task_id, int(time.time() - start))
                if on_progress:
                    on_progress("done", {"zip_url": zip_url})
                return zip_url

            if state == MinerUTaskState.FAILED:
                err_msg = result.get("err_msg", "未知错误")
                logger.error("任务失败: %s - %s", task_id, err_msg)
                raise RuntimeError(f"MinerU 解析失败: {err_msg}")

            # 进行中
            progress_info = result.get("extract_progress", {})
            if on_progress:
                on_progress(state, progress_info)

            elapsed = int(time.time() - start)
            logger.info("[%ds] 任务 %s 状态: %s", elapsed, task_id, state)
            time.sleep(self.poll_interval)

        raise RuntimeError(f"轮询超时 ({self.poll_timeout}s)，task_id={task_id}")

    def wait_for_batch(
        self,
        batch_id: str,
        file_name: str,
        on_progress: Any | None = None,
    ) -> str:
        """轮询批量任务中指定文件直到完成

        Args:
            batch_id: 批量任务 ID
            file_name: 目标文件名
            on_progress: 回调函数

        Returns:
            full_zip_url: 结果 ZIP 包下载地址

        Raises:
            RuntimeError: 任务失败或超时
        """
        logger.info("开始轮询批量任务: %s (文件: %s)", batch_id, file_name)
        start = time.time()

        while time.time() - start < self.poll_timeout:
            results = self.get_batch_status(batch_id)

            for item in results:
                if item.get("file_name") != file_name:
                    continue

                state = item.get("state", "")

                if state == MinerUTaskState.DONE:
                    zip_url = item.get("full_zip_url", "")
                    logger.info("批量任务完成: %s/%s (耗时 %ds)", batch_id, file_name, int(time.time() - start))
                    if on_progress:
                        on_progress("done", {"zip_url": zip_url})
                    return zip_url

                if state == MinerUTaskState.FAILED:
                    err_msg = item.get("err_msg", "未知错误")
                    logger.error("批量任务失败: %s/%s - %s", batch_id, file_name, err_msg)
                    raise RuntimeError(f"MinerU 解析失败: {err_msg}")

                if on_progress:
                    progress_info = item.get("extract_progress", {})
                    on_progress(state, progress_info)

            elapsed = int(time.time() - start)
            logger.info("[%ds] 批量任务 %s 状态: %s", elapsed, batch_id, state if "state" in locals() else "unknown")
            time.sleep(self.poll_interval)

        raise RuntimeError(f"轮询超时 ({self.poll_timeout}s)，batch_id={batch_id}")

    # ──────────────────────────────────────────────
    # 5. 下载并提取结果
    # ──────────────────────────────────────────────

    def download_and_extract(
        self,
        zip_url: str,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        """下载 ZIP 结果包并解压

        ZIP 包含: full.md (Markdown), *.json (中间结果), images/

        Args:
            zip_url: ZIP 下载 URL
            output_dir: 解压目录

        Returns:
            包含 markdown_path, json_files, image_dir 的字典

        Raises:
            RuntimeError: 下载或解压失败
        """
        output_dir = ensure_dir(output_dir)

        logger.info("下载结果 ZIP: %s", zip_url[:80] + "...")
        resp = requests.get(zip_url, timeout=self.timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"下载 ZIP 失败: HTTP {resp.status_code}")

        try:
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                zf.extractall(output_dir)
                names = zf.namelist()
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"ZIP 解压失败: {e}") from e

        # 查找 Markdown、DOCX 文件
        md_files = [f for f in names if f.endswith(".md")]
        json_files = [f for f in names if f.endswith(".json")]
        docx_files = [f for f in names if f.endswith(".docx") and "formatted" not in f.lower()]
        # 推断图片目录：查找路径中包含 images 的目录名
        image_dirs = set()
        for f in names:
            parts = f.split("/")
            if len(parts) > 1 and "image" in parts[0].lower():
                image_dirs.add(parts[0] + "/")
        image_dirs = list(image_dirs)

        markdown_path = None
        # 优先查找 full.md
        for f in md_files:
            if Path(f).name == "full.md":
                markdown_path = str(output_dir / f)
                break
        if not markdown_path and md_files:
            markdown_path = str(output_dir / md_files[0])

        logger.info("解压完成: %d 文件, markdown=%s", len(names), markdown_path)

        # 查找 MinerU 提供的 DOCX 文件（extra_formats 输出）
        mineru_docx_path = None
        if docx_files:
            # 优先查找名为 full.docx 的文件
            for f in docx_files:
                if Path(f).name == "full.docx":
                    mineru_docx_path = str(output_dir / f)
                    break
            if not mineru_docx_path:
                mineru_docx_path = str(output_dir / docx_files[0])
            logger.info("MinerU DOCX 文件: %s", mineru_docx_path)

        return {
            "markdown_path": markdown_path,
            "markdown_content": Path(markdown_path).read_text(encoding="utf-8") if markdown_path else "",
            "json_files": [str(output_dir / f) for f in json_files],
            "image_dir": str(output_dir / image_dirs[0]) if image_dirs else None,
            "all_files": names,
            "extract_dir": str(output_dir),
            "mineru_docx_path": mineru_docx_path,
        }

    # ──────────────────────────────────────────────
    # 6. 高级接口：一步到位解析
    # ──────────────────────────────────────────────

    def parse_file(
        self,
        file_path: str | Path,
        output_dir: str | Path | None = None,
        model_version: str = MinerUModelVersion.VLM,
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: str | None = None,
        extra_formats: list[str] | None = None,
        on_progress: Any | None = None,
    ) -> dict[str, Any]:
        """一步到位：上传本地文件 → 轮询 → 下载 → 提取 Markdown

        Args:
            file_path: 本地 PDF/图片等文件路径
            output_dir: 结果解压目录，为 None 时自动生成
            model_version: 模型版本
            is_ocr: 是否启用 OCR
            enable_formula: 是否启用公式识别
            enable_table: 是否启用表格识别
            language: 文档语言
            page_ranges: 页码范围
            on_progress: 进度回调 (stage, info) -> None

        Returns:
            download_and_extract 的返回结果

        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: API 调用失败
        """
        file_path = Path(file_path)
        if output_dir is None:
            output_dir = file_path.parent / f"{file_path.stem}_mineru_output"

        if on_progress:
            on_progress("uploading", {"file": file_path.name})

        batch_id, file_name = self.create_task_by_file(
            file_path,
            model_version=model_version,
            is_ocr=is_ocr,
            enable_formula=enable_formula,
            enable_table=enable_table,
            language=language,
            page_ranges=page_ranges,
            extra_formats=extra_formats,
        )

        zip_url = self.wait_for_batch(batch_id, file_name, on_progress=on_progress)

        return self.download_and_extract(zip_url, output_dir)

    def parse_url(
        self,
        file_url: str,
        output_dir: str | Path,
        model_version: str = MinerUModelVersion.VLM,
        is_ocr: bool = False,
        enable_formula: bool = True,
        enable_table: bool = True,
        language: str = "ch",
        page_ranges: str | None = None,
        on_progress: Any | None = None,
    ) -> dict[str, Any]:
        """一步到位：URL 提交 → 轮询 → 下载 → 提取 Markdown

        Args:
            file_url: 文件的公开访问 URL
            output_dir: 结果解压目录
            model_version: 模型版本
            其他参数同 parse_file

        Returns:
            download_and_extract 的返回结果
        """
        if on_progress:
            on_progress("submitting", {"url": file_url})

        task_id = self.create_task_by_url(
            file_url,
            model_version=model_version,
            is_ocr=is_ocr,
            enable_formula=enable_formula,
            enable_table=enable_table,
            language=language,
            page_ranges=page_ranges,
        )

        zip_url = self.wait_for_task(task_id, on_progress=on_progress)

        return self.download_and_extract(zip_url, output_dir)
