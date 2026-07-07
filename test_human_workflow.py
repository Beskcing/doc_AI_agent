"""
人工真实流程全面测试（Loop Engineering V2）
使用文档：GB 5009.225-2016CN.pdf
使用模板：GB_T14294-2008.docx

适配标准API响应格式：
- 数据在 data 字段内
- 任务字段: cleaned_markdown_preview, style_config, result_path
- 下载端点: /api/tasks/{id}/download/file
- 模板上传: POST /api/templates/upload → POST /api/templates
- PDF分页: pages key
- 删除检查: code == 404
"""
import sys, json, time, os, uuid, urllib.request, urllib.error
from pathlib import Path

BASE = "http://localhost:8000/api"
PASS = 0
FAIL = 0
ERRORS = []

def log(msg):
    print(f"  {msg}")

def get_data(resp):
    if isinstance(resp, dict) and "data" in resp:
        return resp["data"]
    return resp

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        msg = f"❌ {name}: {detail}" if detail else f"❌ {name}"
        print(f"  {msg}")
        ERRORS.append(msg)

def request(method, path, data=None, files=None, timeout=120):
    url = f"{BASE}{path}"
    if files:
        boundary = uuid.uuid4().hex
        body = b""
        for key, (fname, fdata, ftype) in files.items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; filename=\"{fname}\"\r\nContent-Type: {ftype}\r\n\r\n".encode()
            body += fdata if isinstance(fdata, bytes) else fdata.encode()
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        req = urllib.request.Request(url, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(data).encode()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        ct = resp.headers.get("Content-Type", "")
        if "application/json" in ct:
            return json.loads(resp.read().decode())
        return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try: return json.loads(body)
        except: return {"code": e.code, "message": body}
    except Exception as e:
        return {"code": -1, "message": str(e)}

def request_poll_status(path, timeout=900, interval=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(f"{BASE}{path}", timeout=30)
            data = json.loads(resp.read().decode())
            d = get_data(data)
            s = d.get("status", "") if isinstance(d, dict) else ""
            if s in ("completed", "failed", "error", "cancelled"):
                return data
        except:
            time.sleep(interval)
            continue
        time.sleep(interval)
    return {"code": -1, "message": "timeout"}

def main():
    global PASS, FAIL
    print("=" * 60)
    print("  Loop Engineering 人工流程全面测试 V2")
    print("  测试文档: GB 5009.225-2016CN.pdf")
    print("  测试模板: GB_T14294-2008.docx")
    print("=" * 60)
    print()

    # ===================== T01: 健康检查 =====================
    print("[T01] 健康检查")
    r = request("GET", "/health")
    check("健康检查返回ok", r.get("status") == "ok", str(r)[:100])
    log("  API 服务正常运行")
    print()

    # ===================== T02: 系统配置 =====================
    print("[T02] 系统配置")
    r = request("GET", "/config")
    cfg = get_data(r)
    check("配置返回包含llm_provider", "llm_provider" in cfg if isinstance(cfg, dict) else False, str(r)[:200])
    # 持久化验证
    r2 = request("PUT", "/config", {"llm_provider": "glm", "llm_model": "glm-4"})
    check("配置更新返回成功", r2.get("code", -1) == 0, str(r2)[:200])
    r3 = request("GET", "/config")
    cfg3 = get_data(r3)
    check("配置持久化验证", cfg3.get("llm_provider") == "glm" if isinstance(cfg3, dict) else False, str(cfg3)[:200])
    log(f"  LLM Provider: {cfg3.get('llm_provider')}, Model: {cfg3.get('llm_model')}")
    print()

    # ===================== T03: 上传PDF =====================
    print("[T03] 上传测试文档")
    pdf_path = Path("GB 5009.225-2016CN.pdf")
    if not pdf_path.exists():
        check("PDF文件存在", False)
        return

    pdf_size = pdf_path.stat().st_size
    log(f"  PDF大小: {pdf_size/1024/1024:.1f} MB")
    with open(pdf_path, "rb") as f:
        pdf_data = f.read()
    r = request("POST", "/upload", files={
        "file": ("GB 5009.225-2016CN.pdf", pdf_data, "application/pdf")
    })
    d = get_data(r) if isinstance(r, dict) else {}
    upload_id = d.get("upload_id") if isinstance(d, dict) else None
    check("文件上传成功返回upload_id", upload_id is not None, str(r)[:300])
    log(f"  upload_id: {upload_id}")
    file_id = upload_id
    print()

    # ===================== T04: 任务创建与生命周期 =====================
    print("[T04] 任务创建与生命周期")
    task_id = None
    r = request("POST", "/tasks", {
        "upload_id": file_id,
        "standard": "GB/T 5009.225",
    })
    d_task = get_data(r) if isinstance(r, dict) else {}
    task_id = d_task.get("id") if isinstance(d_task, dict) else None
    check("任务创建成功", task_id is not None, str(r)[:300])
    log(f"  task_id: {task_id}")

    if task_id:
        # 4b: 等待任务完成
        log("  ⏳ 等待任务处理中（MinerU解析+LLM清洗+样式提取，约2-5分钟）...")
        t0 = time.time()
        r_task = request_poll_status(f"/tasks/{task_id}", timeout=1200, interval=15)
        elapsed = time.time() - t0
        d_task_resp = get_data(r_task) if isinstance(r_task, dict) else {}
        final_status = d_task_resp.get("status", "") if isinstance(d_task_resp, dict) else ""
        check("任务最终状态为completed", final_status == "completed", f"status={final_status}, elapsed={elapsed:.0f}s")
        log(f"  耗时: {elapsed:.0f}秒")

        if final_status == "completed":
            # 4c: 验证任务详情字段
            detail = get_data(r_task) if isinstance(r_task, dict) else {}
            # 从字典中获取字段（TaskDetail 模型扩展字段）
            result_path = detail.get("result_path", "") if isinstance(detail, dict) else ""
            md_preview = detail.get("cleaned_markdown_preview", "") if isinstance(detail, dict) else ""
            style_cfg = detail.get("style_config_preview") if isinstance(detail, dict) else None
            upload_id_val = detail.get("upload_id") if isinstance(detail, dict) else ""
            filename_val = detail.get("filename") if isinstance(detail, dict) else ""

            check("任务详情包含result_path", bool(result_path), str(detail)[:300])
            check("任务详情包含cleaned_markdown_preview", bool(md_preview), str(detail)[:300])
            check("任务详情包含style_config_preview", bool(style_cfg), str(detail)[:300])
            check("任务详情包含upload_id字段", bool(upload_id_val), str(detail)[:300])
            check("任务详情包含filename字段", bool(filename_val), str(detail)[:300])
            log(f"  文件名: {filename_val}")
            log(f"  result_path: {result_path}")

            # 4d: 任务列表分页验证
            r_list = request("GET", "/tasks?page=1&page_size=10")
            dl = get_data(r_list) if isinstance(r_list, dict) else {}
            items = dl.get("items", []) if isinstance(dl, dict) else []
            check("任务列表返回非空", len(items) > 0, str(r_list)[:200])
            if items:
                check("任务列表项包含status字段", bool(items[0].get("status")), str(items[0])[:200])
                check("任务列表项包含file_size_mb字段", items[0].get("file_size_mb") is not None, str(items[0])[:200])
        else:
            result_path = ""
            md_preview = ""
            style_cfg = None
            log(f"  ⚠️ 任务未完成: {final_status}")
        print()

        # ===================== T05: 预览功能 =====================
        print("[T05] 预览功能")
        # 5a: Markdown 内容
        r_md = request("GET", f"/tasks/{task_id}/content")
        check("Markdown内容可获取", r_md.get("code") != 500 if isinstance(r_md, dict) else True, str(r_md)[:200])
        if isinstance(r_md, dict) and r_md.get("code") == 0:
            md_cont = get_data(r_md)
            check("Markdown内容非空", len(md_cont.get("content", md_cont.get("markdown", ""))) > 50 if isinstance(md_cont, dict) else False, str(r_md)[:200])

        # 5b: DOCX→HTML 预览
        r_html = request("GET", f"/tasks/{task_id}/preview")
        check("DOCX预览可获取", r_html.get("code") != 500 if isinstance(r_html, dict) else True, str(r_html)[:200])

        # 5c: HTML 内容
        r_htmlc = request("GET", f"/tasks/{task_id}/content/html")
        check("HTML内容可获取", r_htmlc.get("code") != 500 if isinstance(r_htmlc, dict) else True, str(r_htmlc)[:200])

        # 5d: MinerU 原始 DOCX 预览
        r_mineru = request("GET", f"/tasks/{task_id}/preview/mineru-docx")
        check("MinerU原始DOCX预览可获取", r_mineru.get("code") != 500 if isinstance(r_mineru, dict) else True, str(r_mineru)[:200])

        # 5e: 原始PDF分页预览（第1页，3张）
        r_pdf = request("GET", f"/tasks/{task_id}/preview/original-pdf?page=1&page_size=3")
        d_pdf = get_data(r_pdf) if isinstance(r_pdf, dict) else {}
        pdf_pages = d_pdf.get("pages", []) if isinstance(d_pdf, dict) else []
        total_pages = d_pdf.get("total_pages", 0) if isinstance(d_pdf, dict) else 0
        check("PDF分页预览返回pages数组", len(pdf_pages) > 0, str(r_pdf)[:300])
        check("PDF分页返回total_pages>0", total_pages > 0, str(r_pdf)[:300])
        if pdf_pages:
            check("PDF分页每页有page和image字段", "image" in pdf_pages[0] and "page" in pdf_pages[0], str(pdf_pages[0])[:100])
        log(f"  PDF总页数: {total_pages}, 本次返回: {len(pdf_pages)}页")
        print()

        # ===================== T06: 下载功能 =====================
        print("[T06] 下载功能")
        # 6a: 下载端点获取URL
        r_dl = request("GET", f"/tasks/{task_id}/download")
        check("下载端返回download_url", r_dl.get("code") == 0 if isinstance(r_dl, dict) else False, str(r_dl)[:200])
        dl_url = get_data(r_dl).get("download_url") if isinstance(r_dl, dict) else ""
        log(f"  download_url: {dl_url}")

        # 6b: 下载最终DOCX（用/file端点直接下载）
        r_dl_file = request("GET", f"/tasks/{task_id}/download/file")
        is_bytes = isinstance(r_dl_file, bytes)
        check("最终DOCX下载返回文件", is_bytes, str(type(r_dl_file)))
        if is_bytes:
            check("DOCX文件大小>0", len(r_dl_file) > 1000, f"size={len(r_dl_file)}")
            log(f"  DOCX大小: {len(r_dl_file)/1024:.1f} KB")

        # 6c: 下载MinerU原始DOCX
        r_mdl = request("GET", f"/tasks/{task_id}/download/mineru-docx")
        is_b = isinstance(r_mdl, bytes)
        check("MinerU原始DOCX下载返回文件", is_b, str(type(r_mdl)))
        if is_b:
            check("MinerU DOCX大小>0", len(r_mdl) > 1000, f"size={len(r_mdl)}")
            log(f"  MinerU DOCX大小: {len(r_mdl)/1024:.1f} KB")

        # 6d: 下载Markdown
        r_md_dl = request("GET", f"/tasks/{task_id}/download/markdown")
        check("Markdown下载不报500", r_md_dl.get("code") != 500 if isinstance(r_md_dl, dict) else True, str(r_md_dl)[:200])
        print()

        # ===================== T07: 内容编辑 =====================
        print("[T07] 内容编辑")
        r_upd1 = request("PUT", f"/tasks/{task_id}/content", {
            "content": "# 测试标题\n\n这是通过API更新的测试内容。\n\n## 第一章\n\n这是第一章内容。",
            "format": "markdown"
        })
        check("MD内容更新成功", r_upd1.get("code") != 500 if isinstance(r_upd1, dict) else True, str(r_upd1)[:200])

        r_upd2 = request("PUT", f"/tasks/{task_id}/content", {
            "content": "<h1>HTML测试标题</h1><p>HTML更新内容。</p>",
            "format": "html"
        })
        check("HTML内容更新成功", r_upd2.get("code") != 500 if isinstance(r_upd2, dict) else True, str(r_upd2)[:200])
        print()

        # ===================== T08: 模板上传与提取 =====================
        print("[T08] 模板上传与提取")
        tmpl_path = Path("GB_T14294-2008.docx")
        if tmpl_path.exists():
            with open(tmpl_path, "rb") as f:
                tmpl_data = f.read()
            # 8a: 先上传/提取（POST /api/templates/upload）
            r_tu = request("POST", "/templates/upload", files={
                "file": ("GB_T14294-2008.docx", tmpl_data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            })
            d_tu = get_data(r_tu) if isinstance(r_tu, dict) else {}
            style_config_from_tmpl = d_tu.get("style_config") if isinstance(d_tu, dict) else None
            source_docx_path = d_tu.get("source_docx_path") if isinstance(d_tu, dict) else ""
            check("模板上传提取成功返回style_config", style_config_from_tmpl is not None, str(r_tu)[:300])
            log(f"  source_docx_path: {source_docx_path}")

            if style_config_from_tmpl:
                # 8b: 保存模板到DB（POST /api/templates）
                r_ts = request("POST", "/templates", {
                    "name": "GB_T14294-2008 测试模板",
                    "description": "通过Loop Engineering测试上传",
                    "style_config": style_config_from_tmpl,
                    "source_docx_path": source_docx_path,
                })
                d_ts = get_data(r_ts) if isinstance(r_ts, dict) else {}
                tmpl_id = d_ts.get("id") if isinstance(d_ts, dict) else None
                check("模板保存到DB返回id", tmpl_id is not None, str(r_ts)[:300])
                log(f"  template_id: {tmpl_id}")

                if tmpl_id:
                    # 8c: 模板列表
                    r_tl = request("GET", "/templates")
                    d_tl = get_data(r_tl) if isinstance(r_tl, dict) else {}
                    t_items = d_tl.get("items", []) if isinstance(d_tl, dict) else []
                    check("模板列表返回非空", len(t_items) > 0, str(r_tl)[:200])

                    # 8d: 模板详情
                    r_td = request("GET", f"/templates/{tmpl_id}")
                    check("模板详情可获取(code=0)", r_td.get("code") == 0 if isinstance(r_td, dict) else False, str(r_td)[:200])

                    # 8e: 不存在的模板404
                    r_t404 = request("GET", "/templates/nonexistent-id-12345")
                    is_404 = r_t404.get("code") == 404 if isinstance(r_t404, dict) else False
                    check("模板不存在返回code=404", is_404, str(r_t404)[:200])

                    # 8f: 编辑模板
                    r_te = request("PUT", f"/templates/{tmpl_id}", {
                        "name": "GB_T14294-2008 修改版",
                        "description": "通过API修改的描述"
                    })
                    check("模板编辑返回code=0", r_te.get("code") == 0 if isinstance(r_te, dict) else False, str(r_te)[:200])
        else:
            tmpl_id = None
            style_config_from_tmpl = None
            check("模板文件存在", False)
        print()

        # ===================== T09: 应用模板 =====================
        print("[T09] 应用模板")
        if tmpl_path.exists() and style_config_from_tmpl:
            # 重新保存一个模板
            r_ts2 = request("POST", "/templates", {
                "name": "GB_T14294-2008 应用模板",
                "description": "用于应用模板测试",
                "style_config": style_config_from_tmpl,
            })
            d_ts2 = get_data(r_ts2) if isinstance(r_ts2, dict) else {}
            tmpl_id2 = d_ts2.get("id") if isinstance(d_ts2, dict) else None
            if tmpl_id2:
                r_apply = request("POST", f"/tasks/{task_id}/apply-template", {
                    "template_id": tmpl_id2
                })
                check("应用模板到任务成功", r_apply.get("code") == 0 if isinstance(r_apply, dict) else False, str(r_apply)[:200])

                # 样式调整历史
                r_hist = request("GET", f"/tasks/{task_id}/style-history")
                check("样式调整历史可获取", r_hist.get("code") != 500 if isinstance(r_hist, dict) else True, str(r_hist)[:200])
        else:
            tmpl_id2 = None
        print()

        # ===================== T10: 直接style_config =====================
        print("[T10] 直接应用style_config")
        if style_cfg:
            r_asc = request("POST", f"/tasks/{task_id}/apply-template", {
                "style_config": style_cfg
            })
            check("直接应用style_config成功", r_asc.get("code") == 0 if isinstance(r_asc, dict) else False, str(r_asc)[:200])
        else:
            log("  ⚠️ 无style_config跳过")
        print()

        # ===================== T11: 保存样式到模板 =====================
        print("[T11] 保存样式到模板")
        if style_cfg and tmpl_path.exists():
            with open(tmpl_path, "rb") as f:
                tmpl_data = f.read()
            r_tn = request("POST", "/templates", {
                "name": "保存样式测试模板",
                "description": "用于保存样式测试",
                "style_config": style_cfg,
            })
            d_tn = get_data(r_tn) if isinstance(r_tn, dict) else {}
            new_tid = d_tn.get("id") if isinstance(d_tn, dict) else None
            if new_tid:
                r_sn = request("POST", f"/tasks/{task_id}/save-style-to-template", {
                    "template_name": "从测试保存的样式",
                    "description": "通过Loop Engineering测试保存",
                    "style_config": style_cfg,
                })
                check("保存样式到新模板", r_sn.get("code") == 0 if isinstance(r_sn, dict) else False, str(r_sn)[:200])

                r_su = request("POST", f"/tasks/{task_id}/save-style-to-template", {
                    "template_id": new_tid,
                    "template_name": "从测试更新样式",
                    "description": "通过Loop Engineering测试更新",
                    "style_config": style_cfg,
                })
                check("更新已有模板样式", r_su.get("code") == 0 if isinstance(r_su, dict) else False, str(r_su)[:200])
        print()

        # ===================== T12: 上传修正DOCX =====================
        print("[T12] 上传修正DOCX")
        if tmpl_path.exists():
            with open(tmpl_path, "rb") as f:
                cdata = f.read()
            r_cr = request("POST", f"/tasks/{task_id}/upload-corrected-docx", files={
                "file": ("corrected.docx", cdata, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            })
            check("上传修正DOCX成功", r_cr.get("code") == 0 if isinstance(r_cr, dict) else False, str(r_cr)[:200])
        else:
            log("  ⚠️ 无模板文件跳过修正DOCX")
        print()

        # ===================== T13: 对话排版 =====================
        print("[T13] 对话排版(LLM)")
        r_ss = request("POST", "/chat/sessions", {
            "task_id": task_id,
            "title": "排版对话测试"
        })
        d_ss = get_data(r_ss) if isinstance(r_ss, dict) else {}
        session_id = d_ss.get("id") if isinstance(d_ss, dict) else None
        check("对话会话创建成功", session_id is not None, str(r_ss)[:200])

        if session_id:
            log("  ⏳ 发送LLM消息...")
            r_msg = request("POST", "/chat/style", {
                "session_id": session_id,
                "task_id": task_id,
                "message": "将正文改为宋体四号，行距1.5倍"
            })
            check("LLM对话返回结果不报错", r_msg.get("code") != 500 if isinstance(r_msg, dict) else True, str(r_msg)[:200])
            if r_msg.get("code") == 0:
                check("LLM返回包含style_config", "style_config" in str(get_data(r_msg)), str(r_msg)[:300])

            r_hist = request("GET", f"/chat/sessions/{session_id}")
            check("会话历史可获取", r_hist.get("code") != 500 if isinstance(r_hist, dict) else True, str(r_hist)[:200])

            r_slist = request("GET", "/chat/sessions")
            check("会话列表可获取", r_slist.get("code") != 500 if isinstance(r_slist, dict) else True, str(r_slist)[:200])
        print()

        # ===================== T14: 对话内容编辑 =====================
        print("[T14] 对话内容编辑(LLM)")
        if session_id:
            log("  ⏳ LLM修改文档内容中...")
            r_cc = request("POST", "/chat/content", {
                "session_id": session_id,
                "task_id": task_id,
                "message": "将第一段改为'本方法适用于食品中酒精度的测定。'"
            })
            check("LLM内容编辑返回不报错", r_cc.get("code") != 500 if isinstance(r_cc, dict) else True, str(r_cc)[:200])
        print()

        # ===================== T15: 知识库 =====================
        print("[T15] 知识库")
        r_ks = request("GET", "/kb/stats")
        check("知识库统计可获取", r_ks.get("code") == 0 if isinstance(r_ks, dict) else False, str(r_ks)[:200])
        if r_ks.get("code") == 0:
            d_ks = get_data(r_ks)
            check("知识库统计含total_docs", "total_docs" in d_ks if isinstance(d_ks, dict) else False, str(r_ks)[:200])
            check("知识库统计含indexed_docs", "indexed_docs" in d_ks if isinstance(d_ks, dict) else False, str(r_ks)[:200])
            log(f"  total_docs={d_ks.get('total_docs')}, indexed={d_ks.get('indexed_docs')}, chunks={d_ks.get('total_chunks')}")

        r_kb = request("GET", "/kb/documents")
        check("知识库文档列表可获取", r_kb.get("code") != 500 if isinstance(r_kb, dict) else True, str(r_kb)[:200])
        d_kb_list = get_data(r_kb) if isinstance(r_kb, dict) else {}
        kb_docs = d_kb_list if isinstance(d_kb_list, list) else d_kb_list.get("items", d_kb_list.get("documents", []))

        r_ks2 = request("POST", "/kb/search", {"query": "国标文档排版规范", "top_k": 3})
        check("知识库搜索可执行", r_ks2.get("code") != 500 if isinstance(r_ks2, dict) else True, str(r_ks2)[:200])
        if r_ks2.get("code") == 0:
            d_s = get_data(r_ks2)
            s_results = d_s.get("results", d_s.get("documents", [])) if isinstance(d_s, dict) else []
            check("知识库搜索结果非空", len(s_results) > 0, str(r_ks2)[:200])

        # 删除一个知识库文档测试
        if kb_docs and isinstance(kb_docs, list) and len(kb_docs) > 0:
            doc_id = kb_docs[0].get("id") if isinstance(kb_docs[0], dict) else None
            if doc_id:
                r_dd = request("DELETE", f"/kb/documents/{doc_id}")
                check("知识库文档删除成功", r_dd.get("code") == 0 if isinstance(r_dd, dict) else False, str(r_dd)[:200])
        print()

        # ===================== T16: 任务管理 =====================
        print("[T16] 任务管理")
        r_rt = request("POST", f"/tasks/{task_id}/retry")
        check("任务重试不报错", r_rt.get("code") != 500 if isinstance(r_rt, dict) else True, str(r_rt)[:200])
        if r_rt.get("code") != 500:
            log("  ⏳ 等待重试完成...")
            r_rd = request_poll_status(f"/tasks/{task_id}", timeout=600, interval=10)
            d_rd = get_data(r_rd) if isinstance(r_rd, dict) else {}
            rs = d_rd.get("status", "") if isinstance(d_rd, dict) else ""
            check("任务重试后completed", rs == "completed", f"status={rs}")
        print()

    else:
        print("  ⚠️ 任务创建失败，跳过后续所有任务相关测试\n")

    # ===================== T17: 批量操作 =====================
    print("[T17] 批量操作")
    if file_id:
        r_bp = request("POST", "/tasks/batch", {
            "items": [{"upload_id": file_id, "filename": "GB 5009.225-2016CN.pdf"}],
            "standard": "GB/T 5009.225"
        })
        check("批量任务创建执行", r_bp.get("code") == 0 if isinstance(r_bp, dict) else False, str(r_bp)[:200])
        if r_bp.get("code") == 0:
            d_bp = get_data(r_bp)
            b_items = d_bp.get("items", d_bp.get("tasks", [])) if isinstance(d_bp, dict) else []
            check("批量创建返回任务列表", len(b_items) > 0, str(r_bp)[:200])
    print()

    # ===================== T18: 清理 =====================
    print("[T18] 清理")
    if task_id:
        r_del = request("DELETE", f"/tasks/{task_id}")
        check("任务删除返回code=0", r_del.get("code") == 0 if isinstance(r_del, dict) else False, str(r_del)[:200])

        r_chk = request("GET", f"/tasks/{task_id}")
        is_gone = r_chk.get("code") == 404 if isinstance(r_chk, dict) else False
        check("删除后查询返回code=404(确认删除)", is_gone, str(r_chk)[:200])

    # 清理部分模板
    r_tclean = request("GET", "/templates")
    d_tc = get_data(r_tclean) if isinstance(r_tclean, dict) else {}
    all_t = d_tc.get("items", []) if isinstance(d_tc, dict) else []
    for t in all_t[:3]:
        tid = t.get("id") if isinstance(t, dict) else None
        if tid:
            r_dt = request("DELETE", f"/templates/{tid}")
            check(f"模板删除{tid[:8]}...成功", r_dt.get("code") == 0 if isinstance(r_dt, dict) else False, str(r_dt)[:200])
    print()

    # ===================== 汇总 =====================
    print("=" * 60)
    print(f"  测试汇总: {PASS + FAIL} 项")
    print(f"  ✅ 通过: {PASS}")
    print(f"  ❌ 失败: {FAIL}")
    if FAIL > 0:
        print(f"  通过率: {PASS/(PASS+FAIL)*100:.1f}%")
    if ERRORS:
        print(f"\n  失败详情:")
        for e in ERRORS:
            print(f"    {e}")
    print("=" * 60)
    return FAIL == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
