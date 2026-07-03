"""MinerU API 客户端单元测试

使用 unittest.mock 模拟 HTTP 请求，测试所有 API 调用路径。
"""

from __future__ import annotations

import io
import json
import zipfile
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.tools.mineru_api_client import (
    MINERU_API_BASE,
    MinerUAPIClient,
    MinerUModelVersion,
    MinerUTaskState,
)


class TestMinerUAPIClientInit:
    """客户端初始化测试"""

    def test_init_with_valid_token(self):
        """有效 Token 初始化"""
        client = MinerUAPIClient(token="test-token-123")
        assert client.token == "test-token-123"
        assert client.base_url == MINERU_API_BASE
        assert client.poll_interval == 5
        assert client.poll_timeout == 600

    def test_init_with_empty_token_raises(self):
        """空 Token 抛出异常"""
        with pytest.raises(ValueError, match="Token 不能为空"):
            MinerUAPIClient(token="")

    def test_init_with_custom_params(self):
        """自定义参数"""
        client = MinerUAPIClient(
            token="abc",
            base_url="https://custom.mineru.net/",
            poll_interval=3,
            poll_timeout=300,
        )
        assert client.base_url == "https://custom.mineru.net"  # 去除尾部斜杠
        assert client.poll_interval == 3
        assert client.poll_timeout == 300

    def test_headers_contain_bearer_token(self):
        """请求头包含 Bearer Token"""
        client = MinerUAPIClient(token="my-secret")
        headers = client._headers
        assert headers["Authorization"] == "Bearer my-secret"
        assert headers["Content-Type"] == "application/json"


class TestCreateTaskByUrl:
    """URL 解析任务创建测试"""

    @patch("src.tools.mineru_api_client.requests.post")
    def test_create_task_success(self, mock_post):
        """成功创建任务"""
        mock_post.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {"task_id": "task-abc-123"},
                "msg": "ok",
            })
        )

        client = MinerUAPIClient(token="test")
        task_id = client.create_task_by_url("https://example.com/doc.pdf")

        assert task_id == "task-abc-123"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "/api/v4/extract/task" in call_args[1].get("url", call_args[0][0] if call_args[0] else "")

    @patch("src.tools.mineru_api_client.requests.post")
    def test_create_task_api_error(self, mock_post):
        """API 返回错误"""
        mock_post.return_value = Mock(
            json=Mock(return_value={"code": -10002, "msg": "参数错误"})
        )

        client = MinerUAPIClient(token="test")
        with pytest.raises(RuntimeError, match="创建解析任务失败"):
            client.create_task_by_url("https://example.com/doc.pdf")

    @patch("src.tools.mineru_api_client.requests.post")
    def test_create_task_with_all_params(self, mock_post):
        """带全部参数的请求"""
        mock_post.return_value = Mock(
            json=Mock(return_value={"code": 0, "data": {"task_id": "t1"}})
        )

        client = MinerUAPIClient(token="test")
        client.create_task_by_url(
            "https://example.com/doc.pdf",
            model_version=MinerUModelVersion.PIPELINE,
            is_ocr=True,
            enable_formula=False,
            enable_table=False,
            language="en",
            page_ranges="1-5",
            extra_formats=["docx", "html"],
        )

        call_kwargs = mock_post.call_args[1]["json"]
        assert call_kwargs["url"] == "https://example.com/doc.pdf"
        assert call_kwargs["model_version"] == "pipeline"
        assert call_kwargs["is_ocr"] is True
        assert call_kwargs["enable_formula"] is False
        assert call_kwargs["language"] == "en"
        assert call_kwargs["page_ranges"] == "1-5"
        assert call_kwargs["extra_formats"] == ["docx", "html"]


class TestCreateTaskByFile:
    """文件上传解析任务创建测试"""

    @patch("src.tools.mineru_api_client.requests.put")
    @patch("src.tools.mineru_api_client.requests.post")
    def test_upload_file_success(self, mock_post, mock_put, tmp_path):
        """成功上传文件"""
        # 创建测试文件
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"%PDF-1.4 test content")

        mock_post.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {
                    "batch_id": "batch-123",
                    "file_urls": ["https://oss.example.com/upload"],
                },
            })
        )
        mock_put.return_value = Mock(status_code=200)

        client = MinerUAPIClient(token="test")
        batch_id, file_name = client.create_task_by_file(test_file)

        assert batch_id == "batch-123"
        assert file_name == "test.pdf"
        mock_post.assert_called_once()
        mock_put.assert_called_once()

    @patch("src.tools.mineru_api_client.requests.post")
    def test_upload_file_not_found(self, mock_post):
        """文件不存在"""
        client = MinerUAPIClient(token="test")
        with pytest.raises(FileNotFoundError):
            client.create_task_by_file("/nonexistent/file.pdf")

    @patch("src.tools.mineru_api_client.requests.put")
    @patch("src.tools.mineru_api_client.requests.post")
    def test_upload_file_put_failed(self, mock_post, mock_put, tmp_path):
        """PUT 上传失败"""
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"content")

        mock_post.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {"batch_id": "b1", "file_urls": ["https://oss.example.com"]},
            })
        )
        mock_put.return_value = Mock(status_code=403, text="Forbidden")

        client = MinerUAPIClient(token="test")
        with pytest.raises(RuntimeError, match="文件上传失败"):
            client.create_task_by_file(test_file)


class TestGetTaskStatus:
    """任务状态查询测试"""

    @patch("src.tools.mineru_api_client.requests.get")
    def test_get_task_running(self, mock_get):
        """查询运行中任务"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {
                    "task_id": "t1",
                    "state": "running",
                    "extract_progress": {"extracted_pages": 3, "total_pages": 10},
                },
            })
        )

        client = MinerUAPIClient(token="test")
        result = client.get_task_status("t1")

        assert result["state"] == "running"
        assert result["extract_progress"]["total_pages"] == 10

    @patch("src.tools.mineru_api_client.requests.get")
    def test_get_task_done(self, mock_get):
        """查询已完成任务"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {
                    "task_id": "t1",
                    "state": "done",
                    "full_zip_url": "https://cdn.example.com/result.zip",
                },
            })
        )

        client = MinerUAPIClient(token="test")
        result = client.get_task_status("t1")

        assert result["state"] == "done"
        assert "full_zip_url" in result

    @patch("src.tools.mineru_api_client.requests.get")
    def test_get_task_failed(self, mock_get):
        """查询失败任务"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {"task_id": "t1", "state": "failed", "err_msg": "文件格式不支持"},
            })
        )

        client = MinerUAPIClient(token="test")
        result = client.get_task_status("t1")
        assert result["state"] == "failed"
        assert result["err_msg"] == "文件格式不支持"

    @patch("src.tools.mineru_api_client.requests.get")
    def test_get_batch_status(self, mock_get):
        """查询批量任务状态"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {
                    "batch_id": "b1",
                    "extract_result": [
                        {"file_name": "a.pdf", "state": "done", "full_zip_url": "https://cdn/a.zip"},
                        {"file_name": "b.pdf", "state": "running"},
                    ],
                },
            })
        )

        client = MinerUAPIClient(token="test")
        results = client.get_batch_status("b1")

        assert len(results) == 2
        assert results[0]["file_name"] == "a.pdf"
        assert results[0]["state"] == "done"
        assert results[1]["state"] == "running"


class TestWaitForTask:
    """轮询等待测试"""

    @patch("src.tools.mineru_api_client.requests.get")
    @patch("src.tools.mineru_api_client.time.sleep")
    def test_wait_for_task_done(self, mock_sleep, mock_get):
        """任务完成"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {
                    "state": "done",
                    "full_zip_url": "https://cdn.example.com/result.zip",
                },
            })
        )

        client = MinerUAPIClient(token="test", poll_interval=0)
        zip_url = client.wait_for_task("t1")

        assert zip_url == "https://cdn.example.com/result.zip"

    @patch("src.tools.mineru_api_client.requests.get")
    @patch("src.tools.mineru_api_client.time.sleep")
    def test_wait_for_task_failed(self, mock_sleep, mock_get):
        """任务失败"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {"state": "failed", "err_msg": "解析失败"},
            })
        )

        client = MinerUAPIClient(token="test", poll_interval=0)
        with pytest.raises(RuntimeError, match="MinerU 解析失败"):
            client.wait_for_task("t1")

    @patch("src.tools.mineru_api_client.requests.get")
    @patch("src.tools.mineru_api_client.time.sleep")
    def test_wait_for_task_timeout(self, mock_sleep, mock_get):
        """轮询超时"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {"state": "running"},
            })
        )

        client = MinerUAPIClient(token="test", poll_interval=0, poll_timeout=0)
        with pytest.raises(RuntimeError, match="轮询超时"):
            client.wait_for_task("t1")

    @patch("src.tools.mineru_api_client.requests.get")
    @patch("src.tools.mineru_api_client.time.sleep")
    def test_wait_for_task_with_progress_callback(self, mock_sleep, mock_get):
        """进度回调"""
        # 第一次返回 running，第二次返回 done
        mock_get.side_effect = [
            Mock(json=Mock(return_value={
                "code": 0, "data": {"state": "running", "extract_progress": {"extracted_pages": 1, "total_pages": 5}},
            })),
            Mock(json=Mock(return_value={
                "code": 0, "data": {"state": "done", "full_zip_url": "https://cdn.example.com/r.zip"},
            })),
        ]

        progress_calls: list[tuple] = []
        client = MinerUAPIClient(token="test", poll_interval=0)
        zip_url = client.wait_for_task("t1", on_progress=lambda s, i: progress_calls.append((s, i)))

        assert zip_url == "https://cdn.example.com/r.zip"
        assert len(progress_calls) == 2
        assert progress_calls[0][0] == "running"
        assert progress_calls[1][0] == "done"


class TestWaitForBatch:
    """批量任务轮询测试"""

    @patch("src.tools.mineru_api_client.requests.get")
    @patch("src.tools.mineru_api_client.time.sleep")
    def test_wait_for_batch_done(self, mock_sleep, mock_get):
        """批量任务完成"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {
                    "extract_result": [
                        {"file_name": "test.pdf", "state": "done", "full_zip_url": "https://cdn.example.com/r.zip"},
                    ],
                },
            })
        )

        client = MinerUAPIClient(token="test", poll_interval=0)
        zip_url = client.wait_for_batch("b1", "test.pdf")

        assert zip_url == "https://cdn.example.com/r.zip"

    @patch("src.tools.mineru_api_client.requests.get")
    @patch("src.tools.mineru_api_client.time.sleep")
    def test_wait_for_batch_file_not_in_results(self, mock_sleep, mock_get):
        """文件不在批量结果中"""
        mock_get.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {"extract_result": []},
            })
        )

        client = MinerUAPIClient(token="test", poll_interval=0, poll_timeout=0)
        with pytest.raises(RuntimeError, match="轮询超时"):
            client.wait_for_batch("b1", "missing.pdf")


class TestDownloadAndExtract:
    """下载解压测试"""

    @patch("src.tools.mineru_api_client.requests.get")
    def test_download_and_extract_success(self, mock_get, tmp_path):
        """成功下载并解压"""
        # 构造模拟 ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("full.md", "# 测试文档\n\n这是内容。")
            zf.writestr("layout.json", '{"layout": []}')
            zf.writestr("images/img1.jpg", b"fake-image-data")

        mock_get.return_value = Mock(status_code=200, content=zip_buffer.getvalue())

        client = MinerUAPIClient(token="test")
        result = client.download_and_extract("https://cdn.example.com/result.zip", tmp_path)

        assert result["markdown_content"] == "# 测试文档\n\n这是内容。"
        assert result["markdown_path"] is not None
        assert len(result["json_files"]) == 1
        assert result["image_dir"] is not None
        assert len(result["all_files"]) == 3

    @patch("src.tools.mineru_api_client.requests.get")
    def test_download_http_error(self, mock_get, tmp_path):
        """下载 HTTP 错误"""
        mock_get.return_value = Mock(status_code=404)

        client = MinerUAPIClient(token="test")
        with pytest.raises(RuntimeError, match="下载 ZIP 失败"):
            client.download_and_extract("https://cdn.example.com/missing.zip", tmp_path)

    @patch("src.tools.mineru_api_client.requests.get")
    def test_download_bad_zip(self, mock_get, tmp_path):
        """无效 ZIP"""
        mock_get.return_value = Mock(status_code=200, content=b"not-a-zip-file")

        client = MinerUAPIClient(token="test")
        with pytest.raises(RuntimeError, match="ZIP 解压失败"):
            client.download_and_extract("https://cdn.example.com/bad.zip", tmp_path)

    @patch("src.tools.mineru_api_client.requests.get")
    def test_download_no_markdown_file(self, mock_get, tmp_path):
        """ZIP 中没有 Markdown 文件"""
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("data.json", '{"data": 1}')

        mock_get.return_value = Mock(status_code=200, content=zip_buffer.getvalue())

        client = MinerUAPIClient(token="test")
        result = client.download_and_extract("https://cdn.example.com/result.zip", tmp_path)

        assert result["markdown_path"] is None
        assert result["markdown_content"] == ""


class TestParseFileHighLevel:
    """高级接口 parse_file 测试"""

    @patch("src.tools.mineru_api_client.requests.get")
    @patch("src.tools.mineru_api_client.requests.put")
    @patch("src.tools.mineru_api_client.requests.post")
    @patch("src.tools.mineru_api_client.time.sleep")
    def test_parse_file_full_flow(self, mock_sleep, mock_post, mock_put, mock_get, tmp_path):
        """完整流程：上传 → 轮询 → 下载 → 提取"""
        # 创建测试 PDF
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"%PDF-1.4 test")

        # Mock POST: 申请上传链接
        mock_post.return_value = Mock(
            json=Mock(return_value={
                "code": 0,
                "data": {"batch_id": "b1", "file_urls": ["https://oss.example.com/upload"]},
            })
        )
        # Mock PUT: 上传文件
        mock_put.return_value = Mock(status_code=200)

        # 构造结果 ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("full.md", "# 解析结果\n\n正文内容。")

        # Mock GET: 轮询 → 完成 → 下载
        mock_get.side_effect = [
            # 第一次轮询: running
            Mock(json=Mock(return_value={
                "code": 0,
                "data": {"extract_result": [{"file_name": "doc.pdf", "state": "running"}]},
            })),
            # 第二次轮询: done
            Mock(json=Mock(return_value={
                "code": 0,
                "data": {"extract_result": [{"file_name": "doc.pdf", "state": "done", "full_zip_url": "https://cdn.example.com/r.zip"}]},
            })),
            # 下载 ZIP
            Mock(status_code=200, content=zip_buffer.getvalue()),
        ]

        client = MinerUAPIClient(token="test", poll_interval=0)
        result = client.parse_file(test_file, output_dir=tmp_path / "output")

        assert result["markdown_content"] == "# 解析结果\n\n正文内容。"
        assert mock_post.call_count == 1
        assert mock_put.call_count == 1
        assert mock_get.call_count == 3


class TestMinerUTaskState:
    """枚举测试"""

    def test_state_values(self):
        assert MinerUTaskState.DONE == "done"
        assert MinerUTaskState.RUNNING == "running"
        assert MinerUTaskState.FAILED == "failed"
        assert MinerUTaskState.PENDING == "pending"
        assert MinerUTaskState.WAITING_FILE == "waiting-file"

    def test_model_version_values(self):
        assert MinerUModelVersion.VLM == "vlm"
        assert MinerUModelVersion.PIPELINE == "pipeline"
        assert MinerUModelVersion.HTML == "MinerU-HTML"
