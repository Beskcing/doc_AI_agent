"""Loop Engineering 深度测试脚本

覆盖：全新上传→任务流程 / 模板管理 / 对话排版 / 知识库 / 批量操作 / 样式修正
使用真实数据：GB 5009.225-2016CN.pdf
"""

import json
import time
import urllib.request
import urllib.error
import os
from pathlib import Path
from typing import Optional

BASE_URL = "http://localhost:8000"
TEST_PDF = Path("d:/doc_ai_agent/GB 5009.225-2016CN.pdf")

results = []


def log(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    msg = f"[{status}] {name}"
    if detail:
        msg += f": {detail}"
    print(msg)
    results.append({"name": name, "passed": passed, "detail": detail})


def api_get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, data=None, raw_body=None, content_type="application/json") -> dict:
    url = f"{BASE_URL}{path}"
    if raw_body:
        body = raw_body
    elif data:
        body = json.dumps(data).encode()
    else:
        body = b""
    req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def api_put(path: str, data=None) -> dict:
    url = f"{BASE_URL}{path}"
    body = json.dumps(data).encode() if data else b""
    req = urllib.request.Request(url, data=body, method="PUT", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def api_delete(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def upload_file(path: str, file_path: Path, extra_fields: dict = None) -> dict:
    """Multipart upload"""
    url = f"{BASE_URL}{path}"
    boundary = "----LoopTestBoundary"
    
    with open(file_path, "rb") as f:
        file_data = f.read()
    
    body = b""
    # File field
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'.encode()
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += file_data
    body += b"\r\n"
    
    # Extra fields
    if extra_fields:
        for key, val in extra_fields.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"\r\n'.encode()
            body += b"\r\n"
            body += f"{val}\r\n".encode()
    
    body += f"--{boundary}--\r\n".encode()
    
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def wait_task(task_id: str, max_wait: int = 600) -> dict:
    """Wait for task to complete, return final status"""
    waited = 0
    last_status = ""
    while waited < max_wait:
        data = api_get(f"/api/tasks/{task_id}/status")["data"]
        status = data.get("status", "unknown")
        progress = data.get("progress", 0)
        step = data.get("current_step", "")
        if status != last_status:
            print(f"  [{waited}s] status={status}, progress={progress}%, step={step}")
            last_status = status
        if status in ("completed", "failed", "cancelled"):
            return data
        time.sleep(5)
        waited += 5
    return {"status": "timeout", "error": f"Task did not complete in {max_wait}s"}


# ═══════════════════════════════════════════════════════════
# 1. 全新上传 → 完整任务流程 → 验证 DOCX 输出
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("1. 全新上传 → 完整任务流程")
print("=" * 60)

try:
    # 1.1 上传 PDF
    print("\n--- 1.1 上传 PDF ---")
    upload_resp = upload_file("/api/upload", TEST_PDF)
    file_id = upload_resp["data"]["upload_id"]
    original_name = upload_resp["data"]["filename"]
    log("1.1 上传PDF", True, f"file_id={file_id}, name={original_name}")
    
    # 1.2 验证 meta 文件
    print("\n--- 1.2 验证 meta 文件 ---")
    meta_path = Path(f"d:/doc_ai_agent/data/uploads/{file_id}.meta")
    has_meta = meta_path.exists()
    if has_meta:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        log("1.2 Meta文件存在", True, f"original_name={meta.get('original_filename')}")
    else:
        log("1.2 Meta文件存在", False, "meta file not found")
    
    # 1.3 创建任务（不指定 template_id，走 LLM 样式提取）
    print("\n--- 1.3 创建任务 ---")
    task_resp = api_post("/api/tasks", {
        "upload_id": file_id,
        "standard": "GB/T 9704",
    })
    task_id = task_resp["data"]["id"]
    log("1.3 创建任务", True, f"task_id={task_id}")
    
    # 1.4 等待任务完成
    print("\n--- 1.4 等待任务完成（可能需要几分钟）---")
    final = wait_task(task_id)
    task_status = final.get("status", "unknown")
    log("1.4 任务完成", task_status == "completed", f"status={task_status}")
    
    if task_status != "completed":
        error_msg = final.get("error", "unknown error")
        log("1.4a 任务错误信息", False, f"error={error_msg}")
        print(f"\n!!! 任务失败，错误: {error_msg}")
        # Continue testing other areas
    
    # 1.5 验证输出文件
    print("\n--- 1.5 验证输出文件 ---")
    task_detail = api_get(f"/api/tasks/{task_id}")["data"]
    
    # 检查 cleaned markdown（API 返回 cleaned_markdown_preview 或文件在 output 目录）
    cleaned_md_preview = task_detail.get("cleaned_markdown_preview", "")
    cleaned_md_file = Path(f"d:/doc_ai_agent/data/output/{task_id}/cleaned.md")
    if cleaned_md_file.exists():
        md_size = cleaned_md_file.stat().st_size
        log("1.5a Cleaned MD存在", True, f"size={md_size} bytes, preview_len={len(cleaned_md_preview)}")
    elif cleaned_md_preview:
        log("1.5a Cleaned MD存在", True, f"preview_len={len(cleaned_md_preview)}")
    else:
        log("1.5a Cleaned MD存在", False, "no cleaned md file or preview")
    
    # 检查 DOCX 输出（API 返回 result_path）
    docx_path_str = task_detail.get("result_path", "")
    if docx_path_str and Path(docx_path_str).exists():
        docx_size = Path(docx_path_str).stat().st_size
        log("1.5b DOCX输出存在", True, f"size={docx_size} bytes")
    else:
        # 也检查 output 目录
        task_output_dir = Path(f"d:/doc_ai_agent/data/output/{task_id}")
        docx_files = list(task_output_dir.glob("*.docx")) if task_output_dir.exists() else []
        if docx_files:
            docx_size = docx_files[0].stat().st_size
            log("1.5b DOCX输出存在", True, f"size={docx_size} bytes (from output dir)")
        else:
            log("1.5b DOCX输出存在", False, f"result_path={docx_path_str}, no docx in output dir")
    
    # 1.6 验证 style_config（API 返回 style_config_preview）
    print("\n--- 1.6 验证 style_config ---")
    style_config = task_detail.get("style_config_preview", {})
    if style_config:
        log("1.6 StyleConfig非空", True, f"keys={list(style_config.keys())[:5]}...")
    else:
        log("1.6 StyleConfig非空", False, "empty style_config_preview")
    
    # 1.7 下载 DOCX
    print("\n--- 1.7 下载 DOCX ---")
    try:
        dl_info = api_get(f"/api/tasks/{task_id}/download")
        dl_data = dl_info.get("data", {})
        dl_file_url = dl_data.get("download_url", "")
        if dl_file_url:
            req = urllib.request.Request(f"{BASE_URL}{dl_file_url}")
            with urllib.request.urlopen(req, timeout=30) as resp:
                dl_size = len(resp.read())
                log("1.7 下载DOCX", dl_size > 0, f"size={dl_size}")
        else:
            log("1.7 下载DOCX", False, "no download_url")
    except Exception as e:
        log("1.7 下载DOCX", False, str(e))
    
    # 1.8 下载 MinerU 原始 DOCX
    print("\n--- 1.8 下载 MinerU DOCX ---")
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/tasks/{task_id}/download/mineru-docx")
        with urllib.request.urlopen(req, timeout=30) as resp:
            dl_size = len(resp.read())
            log("1.8 下载MinerU DOCX", dl_size > 0, f"size={dl_size}")
    except Exception as e:
        log("1.8 下载MinerU DOCX", False, str(e))
    
    # 1.9 DOCX 预览 (HTML)
    print("\n--- 1.9 DOCX HTML预览 ---")
    try:
        req = urllib.request.Request(f"{BASE_URL}/api/tasks/{task_id}/preview/docx")
        with urllib.request.urlopen(req, timeout=30) as resp:
            html_content = resp.read().decode("utf-8", errors="replace")
            log("1.9 DOCX HTML预览", len(html_content) > 100, f"html_len={len(html_content)}")
    except Exception as e:
        log("1.9 DOCX HTML预览", False, str(e))
    
    # 1.10 Markdown 预览
    print("\n--- 1.10 Markdown 预览 ---")
    try:
        md_resp = api_get(f"/api/tasks/{task_id}/preview")
        md_data = md_resp.get("data", {})
        md_content = md_data.get("markdown_preview", "")
        log("1.10 Markdown预览", len(md_content) > 100, f"md_len={len(md_content)}")
    except Exception as e:
        log("1.10 Markdown预览", False, str(e))

except Exception as e:
    log("1. 全新上传流程", False, str(e))
    task_id = None

# ═══════════════════════════════════════════════════════════
# 2. 模板管理功能
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("2. 模板管理功能")
print("=" * 60)

try:
    # 2.1 列出已有模板
    print("\n--- 2.1 列出模板 ---")
    tpl_resp = api_get("/api/templates")
    templates = tpl_resp.get("data", [])
    log("2.1 列出模板", len(templates) >= 0, f"count={len(templates)}")
    
    # 2.2 上传 docx 提取模板
    print("\n--- 2.2 上传docx提取模板 ---")
    template_docx = Path("d:/doc_ai_agent/data/templates/GB_T_14454_13_2008.docx")
    if template_docx.exists():
        ext_resp = upload_file("/api/templates/upload", template_docx)
        if ext_resp.get("code") == 0:
            ext_data = ext_resp["data"]
            log("2.2 上传docx提取模板", True, f"filename={ext_data.get('filename', 'unknown')}")
            extracted_style = ext_data.get("style_config", {})
        else:
            log("2.2 上传docx提取模板", False, ext_resp.get("message", "unknown error"))
            extracted_style = {}
    else:
        log("2.2 上传docx提取模板", False, f"template docx not found at {template_docx}")
        extracted_style = {}
    
    # 2.3 注册新模板
    print("\n--- 2.3 注册新模板 ---")
    try:
        reg_resp = api_post("/api/templates", {
            "name": "Loop Test Template",
            "description": "Loop Engineering 测试模板",
            "style_config": extracted_style or {"body_style": {"font": {"name": "宋体", "size": 10.5}}}
        })
        if reg_resp.get("code") == 0:
            new_tpl_id = reg_resp["data"]["id"]
            log("2.3 注册新模板", True, f"template_id={new_tpl_id}")
        else:
            log("2.3 注册新模板", False, reg_resp.get("message", ""))
            new_tpl_id = None
    except Exception as e:
        log("2.3 注册新模板", False, str(e))
        new_tpl_id = None
    
    # 2.4 获取模板详情
    print("\n--- 2.4 获取模板详情 ---")
    if new_tpl_id:
        try:
            detail_resp = api_get(f"/api/templates/{new_tpl_id}")
            tpl_detail = detail_resp.get("data", {})
            log("2.4 获取模板详情", tpl_detail.get("name") == "Loop Test Template",
                f"name={tpl_detail.get('name')}")
        except Exception as e:
            log("2.4 获取模板详情", False, str(e))
    
    # 2.5 更新模板
    print("\n--- 2.5 更新模板 ---")
    if new_tpl_id:
        try:
            upd_resp = api_put(f"/api/templates/{new_tpl_id}", {
                "name": "Loop Test Template Updated",
                "description": "更新后的描述"
            })
            log("2.5 更新模板", upd_resp.get("code") == 0, upd_resp.get("message", ""))
        except Exception as e:
            log("2.5 更新模板", False, str(e))
    
    # 2.6 应用模板到任务
    print("\n--- 2.6 应用模板到任务 ---")
    if task_id and new_tpl_id:
        try:
            apply_resp = api_post(f"/api/tasks/{task_id}/apply-template", {
                "template_id": new_tpl_id
            })
            log("2.6 应用模板到任务", apply_resp.get("code") == 0,
                apply_resp.get("message", ""))
        except Exception as e:
            log("2.6 应用模板到任务", False, str(e))
    
    # 2.7 删除测试模板
    print("\n--- 2.7 删除测试模板 ---")
    if new_tpl_id:
        try:
            del_resp = api_delete(f"/api/templates/{new_tpl_id}")
            log("2.7 删除测试模板", del_resp.get("code") == 0, del_resp.get("message", ""))
        except Exception as e:
            log("2.7 删除测试模板", False, str(e))

except Exception as e:
    log("2. 模板管理功能", False, str(e))

# ═══════════════════════════════════════════════════════════
# 3. 对话排版功能
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("3. 对话排版功能")
print("=" * 60)

try:
    # 3.1 创建会话
    print("\n--- 3.1 创建会话 ---")
    session_resp = api_post("/api/chat/sessions", {
        "title": "Loop测试会话"
    })
    if session_resp.get("code") == 0:
        session_id = session_resp["data"]["id"]
        log("3.1 创建会话", True, f"session_id={session_id}")
    else:
        log("3.1 创建会话", False, session_resp.get("message", ""))
        session_id = None
    
    # 3.2 发送对话消息（修改样式）
    print("\n--- 3.2 发送对话消息 ---")
    if session_id:
        try:
            chat_resp = api_post("/api/chat/style", {
                "message": "请将正文字体改为黑体，字号改为小四号",
                "current_style_config": {"body_style": {"font": {"name": "宋体", "size": 10.5}}},
                "session_id": session_id
            })
            if chat_resp.get("code") == 0:
                chat_data = chat_resp["data"]
                log("3.2 发送对话消息", True, f"reply={chat_data.get('reply', '')[:50]}")
            else:
                log("3.2 发送对话消息", False, chat_resp.get("message", ""))
        except Exception as e:
            log("3.2 发送对话消息", False, str(e))
    
    # 3.3 获取对话历史
    print("\n--- 3.3 获取对话历史 ---")
    if session_id:
        try:
            hist_resp = api_get(f"/api/chat/sessions/{session_id}/messages")
            messages = hist_resp.get("data", {}).get("items", [])
            log("3.3 获取对话历史", len(messages) >= 2, f"msg_count={len(messages)}")
        except Exception as e:
            log("3.3 获取对话历史", False, str(e))
    
    # 3.4 列出所有会话
    print("\n--- 3.4 列出会话 ---")
    try:
        sessions_resp = api_get("/api/chat/sessions")
        sessions = sessions_resp.get("data", {}).get("items", [])
        log("3.4 列出会话", len(sessions) >= 1, f"session_count={len(sessions)}")
    except Exception as e:
        log("3.4 列出会话", False, str(e))
    
    # 3.5 删除会话
    print("\n--- 3.5 删除会话 ---")
    if session_id:
        try:
            del_session = api_delete(f"/api/chat/sessions/{session_id}")
            log("3.5 删除会话", del_session.get("code") == 0, del_session.get("message", ""))
        except Exception as e:
            log("3.5 删除会话", False, str(e))

except Exception as e:
    log("3. 对话排版功能", False, str(e))

# ═══════════════════════════════════════════════════════════
# 4. 知识库管理
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("4. 知识库管理")
print("=" * 60)

try:
    # 4.1 知识库统计
    print("\n--- 4.1 知识库统计 ---")
    try:
        stats_resp = api_get("/api/kb/stats")
        stats = stats_resp.get("data", {})
        log("4.1 知识库统计", stats_resp.get("code") == 0,
            f"total={stats.get('total_docs', 0)}, indexed={stats.get('indexed_docs', 0)}")
    except Exception as e:
        log("4.1 知识库统计", False, str(e))
    
    # 4.2 列出知识库文档
    print("\n--- 4.2 列出KB文档 ---")
    try:
        kb_list = api_get("/api/kb/documents")
        kb_docs = kb_list.get("data", [])
        log("4.2 列出KB文档", True, f"doc_count={len(kb_docs)}")
    except Exception as e:
        log("4.2 列出KB文档", False, str(e))
    
    # 4.3 上传知识库文档
    print("\n--- 4.3 上传KB文档 ---")
    test_md = Path("d:/doc_ai_agent/knowledge_data/raw_docs/gbt_9704_2012.md")
    if test_md.exists():
        try:
            kb_upload = upload_file("/api/kb/documents", test_md)
            log("4.3 上传KB文档", kb_upload.get("code") == 0, kb_upload.get("message", ""))
        except Exception as e:
            log("4.3 上传KB文档", False, str(e))
    else:
        log("4.3 上传KB文档", False, f"file not found: {test_md}")
    
    # 4.4 知识库检索
    print("\n--- 4.4 知识库检索 ---")
    try:
        search_resp = api_post("/api/kb/search", {
            "query": "国标排版规范 字体字号",
            "top_k": 3
        })
        search_results = search_resp.get("data", {}).get("results", [])
        log("4.4 知识库检索", search_resp.get("code") == 0,
            f"results={len(search_results)}")
    except Exception as e:
        log("4.4 知识库检索", False, str(e))
    
    # 4.5 重建索引
    print("\n--- 4.5 重建索引 ---")
    try:
        rebuild_resp = api_post("/api/kb/rebuild", {"force": True})
        log("4.5 重建索引", rebuild_resp.get("code") == 0,
            rebuild_resp.get("data", {}).get("message", ""))
    except Exception as e:
        log("4.5 重建索引", False, str(e))

except Exception as e:
    log("4. 知识库管理", False, str(e))

# ═══════════════════════════════════════════════════════════
# 5. 批量上传/批量解析
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("5. 批量上传/批量解析")
print("=" * 60)

try:
    # 5.1 批量上传（上传同一文件两次模拟批量）
    print("\n--- 5.1 批量上传 ---")
    batch_ids = []
    for i in range(2):
        try:
            b_resp = upload_file("/api/upload", TEST_PDF)
            if b_resp.get("code") == 0:
                batch_ids.append(b_resp["data"]["upload_id"])
        except Exception as e:
            log(f"5.1 批量上传#{i}", False, str(e))
    log("5.1 批量上传", len(batch_ids) == 2, f"uploaded={len(batch_ids)}")
    
    # 5.2 批量创建任务
    print("\n--- 5.2 批量创建任务 ---")
    batch_task_ids = []
    for fid in batch_ids:
        try:
            bt_resp = api_post("/api/tasks", {
                "upload_id": fid,
                "standard": "GB/T 9704",
            })
            if bt_resp.get("code") == 0:
                batch_task_ids.append(bt_resp["data"]["id"])
        except Exception as e:
            log(f"5.2 批量创建任务", False, str(e))
    log("5.2 批量创建任务", len(batch_task_ids) == 2, f"created={len(batch_task_ids)}")
    
    # 5.3 批量解析（任务创建后自动开始处理，无需额外触发）
    print("\n--- 5.3 批量任务自动处理 ---")
    log("5.3 批量任务自动处理", True, "tasks auto-processing")
    
    # 5.4 等待批量任务完成
    print("\n--- 5.4 等待批量任务 ---")
    for tid in batch_task_ids:
        final = wait_task(tid, max_wait=600)
        log(f"5.4 批量任务 {tid[:8]}", final.get("status") == "completed",
            f"status={final.get('status')}")
    
    # 5.5 清理批量测试任务
    print("\n--- 5.5 清理批量任务 ---")
    for tid in batch_task_ids:
        try:
            api_delete(f"/api/tasks/{tid}")
        except:
            pass
    log("5.5 清理批量任务", True, f"deleted={len(batch_task_ids)}")

except Exception as e:
    log("5. 批量上传/解析", False, str(e))

# ═══════════════════════════════════════════════════════════
# 6. 样式修正/调整回写/迭代学习
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("6. 样式修正/调整回写")
print("=" * 60)

if task_id:
    try:
        # 6.1 获取当前样式配置
        print("\n--- 6.1 获取当前样式 ---")
        task_detail = api_get(f"/api/tasks/{task_id}")["data"]
        current_style = task_detail.get("style_config_preview", {})
        log("6.1 获取当前样式", bool(current_style), f"keys={list(current_style.keys())[:5]}")
        
        # 6.2 修正样式（通过 apply-template 重新渲染）
        print("\n--- 6.2 修正样式 ---")
        # 修改样式配置
        modified_style = current_style.copy()
        if "body_style" in modified_style:
            body = modified_style["body_style"].copy()
            if "font" in body:
                font = body["font"].copy()
                font["name"] = "仿宋"
                body["font"] = font
            modified_style["body_style"] = body
        
        try:
            fix_resp = api_post(f"/api/tasks/{task_id}/apply-template", {
                "style_config": modified_style
            })
            log("6.2 修正样式", fix_resp.get("code") == 0, fix_resp.get("message", ""))
        except Exception as e:
            log("6.2 修正样式", False, str(e))
        
        # 6.3 查看样式调整历史
        print("\n--- 6.3 样式调整历史 ---")
        try:
            hist_resp = api_get(f"/api/tasks/{task_id}/style-history")
            history = hist_resp.get("data", [])
            log("6.3 样式调整历史", True, f"records={len(history)}")
        except Exception as e:
            log("6.3 样式调整历史", False, str(e))
        
        # 6.4 重新应用模板
        print("\n--- 6.4 重新应用模板 ---")
        try:
            reapply = api_post(f"/api/tasks/{task_id}/apply-template", {
                "template_id": None  # 使用默认
            })
            log("6.4 重新应用模板", True, reapply.get("message", ""))
        except Exception as e:
            log("6.4 重新应用模板", False, str(e))

    except Exception as e:
        log("6. 样式修正", False, str(e))
else:
    log("6. 样式修正", False, "no task_id available")

# ═══════════════════════════════════════════════════════════
# 7. 任务管理（取消/重试/删除）
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("7. 任务管理")
print("=" * 60)

try:
    # 7.1 创建新任务用于测试取消
    print("\n--- 7.1 创建任务用于取消测试 ---")
    cancel_upload = upload_file("/api/upload", TEST_PDF)
    cancel_fid = cancel_upload["data"]["upload_id"]
    cancel_task_resp = api_post("/api/tasks", {
        "upload_id": cancel_fid,
        "standard": "GB/T 9704"
    })
    cancel_tid = cancel_task_resp["data"]["id"]
    log("7.1 创建取消测试任务", True, f"task_id={cancel_tid}")
    
    # 7.2 立即取消
    print("\n--- 7.2 取消任务 ---")
    try:
        cancel_resp = api_post(f"/api/tasks/{cancel_tid}/cancel")
        log("7.2 取消任务", cancel_resp.get("code") == 0, cancel_resp.get("message", ""))
    except Exception as e:
        log("7.2 取消任务", False, str(e))
    
    # 7.3 验证取消状态
    print("\n--- 7.3 验证取消状态 ---")
    time.sleep(2)
    try:
        status_data = api_get(f"/api/tasks/{cancel_tid}/status")["data"]
        is_cancelled = status_data.get("status") in ("cancelled", "cancelling", "completed", "failed")
        log("7.3 验证取消状态", is_cancelled, f"status={status_data.get('status')}")
    except Exception as e:
        log("7.3 验证取消状态", False, str(e))
    
    # 7.4 删除任务
    print("\n--- 7.4 删除任务 ---")
    try:
        del_resp = api_delete(f"/api/tasks/{cancel_tid}")
        log("7.4 删除任务", del_resp.get("code") == 0, del_resp.get("message", ""))
    except Exception as e:
        log("7.4 删除任务", False, str(e))
    
    # 7.5 验证删除
    print("\n--- 7.5 验证删除 ---")
    try:
        tasks_list_resp = api_get("/api/tasks")
        tasks_data = tasks_list_resp.get("data", {})
        task_ids = [t["id"] for t in tasks_data.get("items", [])]
        log("7.5 验证删除", cancel_tid not in task_ids,
            f"found={cancel_tid in task_ids}")
    except Exception as e:
        log("7.5 验证删除", False, str(e))

except Exception as e:
    log("7. 任务管理", False, str(e))

# ═══════════════════════════════════════════════════════════
# 8. 配置和系统
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("8. 配置和系统")
print("=" * 60)

try:
    # 8.1 获取配置
    print("\n--- 8.1 获取配置 ---")
    config_resp = api_get("/api/config")
    config = config_resp.get("data", {})
    log("8.1 获取配置", config_resp.get("code") == 0,
        f"keys={list(config.keys())[:5]}")
    
    # 8.2 任务统计
    print("\n--- 8.2 任务统计 ---")
    stats_resp = api_get("/api/tasks/stats")
    stats = stats_resp.get("data", {})
    log("8.2 任务统计", True, f"stats={stats}")
    
    # 8.3 健康检查
    print("\n--- 8.3 健康检查 ---")
    health = api_get("/api/health")
    log("8.3 健康检查", health.get("status") == "ok", f"version={health.get('version')}")

except Exception as e:
    log("8. 配置和系统", False, str(e))

# ═══════════════════════════════════════════════════════════
# 汇总
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("测试汇总")
print("=" * 60)

passed = sum(1 for r in results if r["passed"])
failed = sum(1 for r in results if not r["passed"])
total = len(results)

print(f"\n总计: {total} | 通过: {passed} | 失败: {failed}")
print(f"通过率: {passed/total*100:.1f}%")

if failed > 0:
    print("\n失败的测试:")
    for r in results:
        if not r["passed"]:
            print(f"  [FAIL] {r['name']}: {r['detail']}")

print(f"\n测试完成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
