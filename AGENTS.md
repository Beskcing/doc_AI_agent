# AGENTS.md - 鍥芥爣鏂囨。鎺掔増鏅鸿兘浣撳伐绋嬭鑼?

浼佷笟绾ф枃妗ｇ粨鏋勫寲涓庢帓鐗堟櫤鑳戒綋锛氳В鏋?MinerU 杈撳嚭鐨?Markdown 鈫?娓呮礂 OCR 鐟曠柕 鈫?RAG 妫€绱㈡帓鐗堣鑼?鈫?LLM 鎻愬彇鏍峰紡 鈫?鐢熸垚鍥芥爣 Word 鏂囨。銆?

## 鎶€鏈爤
LangChain/LangGraph (缂栨帓) + Qwen/GLM (LLM) + MinerU (PDF瑙ｆ瀽) + Pandoc/python-docx (娓叉煋) + FastAPI (API) + React/Ant Design (鍓嶇) + SQLite/SQLAlchemy (DB) + Chroma (RAG鍚戦噺搴?

## 鍚姩鏂瑰紡
- Docker 閮ㄧ讲锛歚docker compose up -d`锛堟瀯寤哄苟鍚姩鍓嶅悗绔級
- 鍚庣 API锛歚python -m scripts.run_server --port 8000`
- 鍓嶇寮€鍙戯細`cd frontend && npm run dev`
- CLI 绠＄嚎锛歚python -m scripts.run_pipeline --input doc.pdf --output output.docx`
- 鍒濆鍖?RAG锛歚python -m scripts.init_knowledge_base`
- 杩愯娴嬭瘯锛歚python -m pytest tests/ -v`

## 鍏抽敭璺緞
- 宸ヤ綔娴侊細`src/workflows/doc_formatting_graph.py` | LLM 灏佽锛歚src/llm_client.py`
- 宸ュ叿閾撅細`src/tools/` (mineru_parser, pandoc_converter, docx_styler, markdown_cleaner, html_table_preserver)
- RAG锛歚src/rag/` | API锛歚src/api/` | DB锛歚src/db/` | 鍓嶇锛歚frontend/`
- 鎻愮ず璇嶏細`prompts/` | 閰嶇疆锛歚configs/settings.yaml` | 鏋舵瀯鏂囨。锛歚docs/ARCHITECTURE.md`

## 宸ョ▼瑙勮寖

1. **鏋舵瀯瑙ｈ€︼紙闃插够瑙夐搧寰嬶級**锛歀LM 鍙緭鍑?JSON/Markdown锛屾枃浠?I/O 鍜屾牱寮忔覆鏌撶敱 Python 宸ュ叿鍑芥暟鎵ц锛屼弗绂?LLM 鐢熸垚 Word XML銆?
2. **RAG 闆嗘垚**锛欳hunk Size 600-800 / Overlap 15%锛屽繀椤绘贩鍚堟绱紙BM25 + 鍚戦噺锛夛紝杈撳嚭鎻愪緵 rag_sources 鏉ユ簮杩芥函銆?
3. **浠ｇ爜涓庢祴璇?*锛歁inerU/Pandoc 鏀瑰姩椤婚檮 PDF 娴嬭瘯鐢ㄤ緥锛屾牳蹇冩覆鏌撳嚱鏁伴』鏈夊崟鍏冩祴璇曪紝鍓嶇椤婚€氳繃 `tsc --noEmit`锛孉PI 鍙樻洿鍚屾鏇存柊 E2E 娴嬭瘯銆?
4. **鏁版嵁搴?*锛歋QLAlchemy 2.0 ORM锛屾ā鍨嬪湪 `src/db/models.py`锛孋RUD 鍦?`src/db/crud.py`锛岃矾鐢卞眰涓嶇洿鎺ユ搷浣?DB銆?
5. **鏂囨。鍚屾**锛氳涓?宸ュ叿閾惧彉鏇存椂鏇存柊 AGENTS.md锛屾柊澧炴帓鐗堣鍒欐洿鏂拌嚦 RAG 鐭ヨ瘑搴撱€?
6. **Git 鎻愪氦锛堝己鍒讹級**锛氭瘡娆″彉鏇村悗 `git add -A` + `git commit`锛堝墠缂€ `feat:/fix:/refactor:/docs:`锛? 鏇存柊 AGENTS.md + `git push origin master`銆傝繙绋嬶細`https://github.com/Beskcing/doc_AI_agent.git`
7. **鍙樻洿鍓嶈璁猴紙寮哄埗锛?*锛氭瘡娆℃兂瑕佷慨鏀规垨澧炲姞鍔熻兘鏃讹紝蹇呴』鍏堜笌鐢ㄦ埛璁ㄨ鏂规銆佽揪鎴愪竴鑷村悗锛屾柟鍙紑濮嬬紪鐮併€備弗绂佹湭缁忚璁虹洿鎺ュ姩鎵嬫敼浠ｇ爜銆?

## MinerU 閰嶇疆
閫氳繃 `configs/settings.yaml` 鐨?`mineru.mode` 鍒囨崲锛歚online`锛堥粯璁わ紝绾夸笂 API锛岄渶 `MINERU_API_TOKEN`锛夋垨 `local`锛坢agic-pdf SDK锛夈€傛ā鍨嬬増鏈粯璁?`vlm`銆傚鎴风锛歚src/tools/mineru_api_client.py`锛岀粺涓€鍏ュ彛锛歚src/tools/mineru_parser.py`銆?

### 瀹屾垚鏍囧噯
- LLM JSON 杈撳嚭閫氳繃 Schema 鏍￠獙锛孯AG 妫€绱㈡棤骞昏
- Pandoc 杞崲鏃犳姤閿欙紝HTML 琛ㄦ牸/LaTeX 鍏紡姝ｇ‘鏄犲皠
- python-docx 鏍峰紡搴旂敤鎴愬姛锛屾枃妗ｉ€氳繃鎺掔増鏍￠獙
- 娴嬭瘯瑕嗙洊鐜?鈮?90%锛孍2E 鍏ㄩ儴閫氳繃
- 鍓嶇 TypeScript 缂栬瘧鏃犻敊璇紝MinerU 瑙ｆ瀽姝ｅ父锛孌B 鎸佷箙鍖栨甯?

## 鍙樻洿璁板綍

| 鏃ユ湡 | 绫诲瀷 | 鎽樿 |
|------|------|------|
| 2026-07-07 | fix | SPA fallback鎷︽埅API璺敱淇(main.py璺敱椤哄簭)+init_db绌鸿縼绉昏〃淇 |
| 2026-07-07 | test | Loop Engineering Docker鍏ㄦ祴璇? API 59/62閫氳繃(95.2%)+鍓嶇7椤垫祻瑙堝櫒鑷姩鍖栧叏閫氳繃 |
| 2026-07-07 | feat | 宸ョ▼鍖朠0: llm_client閲嶈瘯+瓒呮椂+LLMResponse token璁℃暟+娴佸紡杈撳嚭+CLI绠＄嚎鍚屾PipelineService |
| 2026-07-07 | refactor | 宸ョ▼鍖朠1: 璺敱灞?2澶凷essionLocal娓呯悊涓篻et_db_session+閰嶇疆鏍￠獙+Alembic杩佺Щ鍒濆鍖?|
| 2026-07-07 | feat | 宸ョ▼鍖朠2: Ruff lint鍏ㄩ€氳繃+pre-commit hooks+鍏ㄥ眬寮傚父澶勭悊+Dockerfile |
| 2026-07-07 | feat | 宸ョ▼鍖朠3: GitHub Actions CI+闄愭祦涓棿浠?Makefile |
| 2026-07-07 | feat | Docker澶氶樁娈垫瀯寤?鍓嶇缂栬瘧+python:3.12-slim+pandoc+docker-compose涓€閿惎鍔?鍚庣SPA闈欐€佹枃浠舵寕杞?|
| 2026-07-07 | config | LLM Provider浠嶲wen鍒囨崲涓烘櫤璋盇I(GLM-4)锛岄粯璁ゆā鍨媑lm-4 |
| 2026-07-07 | fix | 瀵硅瘽LLM澶辫触鏃惰嚜鍔ㄥ洖婊氬绔嬬敤鎴锋秷鎭紝ChatMessageCRUD鏂板delete鏂规硶 |
| 2026-07-07 | feat | html_to_pipe鏀寔colspan/rowspan鍚堝苟鍗曞厓鏍?|
| 2026-07-07 | perf | hybrid_retriever _find_doc_index O(n)鈫扥(1)鍝堝笇绱㈠紩 |
| 2026-07-07 | fix | markdown_cleaner 鍒嗘LLM瀹℃煡+鍏ㄨ鏍囩偣淇濈暀 |
| 2026-07-07 | feat | docx_styler 5绉嶆柊瑙掕壊澶勭悊(灏侀潰/鍓嶈█/闄勫綍鏍囬/闄勫綍鏉℃/琛ㄦ牸鏍囬)+鍐呭妯″紡璇嗗埆鍚庡 |
| 2026-07-07 | refactor | TaskManager 闂ㄩ潰鎷嗗垎锛氭柊澧濸ipelineService/PreviewService/ContentEditService/ServiceDeps+DB浼氳瘽绠＄悊鍣紝1742鈫?00琛?|
| 2026-07-06 | feat | PDF瀵规瘮棰勮+鍒嗛〉鍔犺浇(109椤礟DF鍝嶅簲浠?5MB闄嶈嚦1MB) |
| 2026-07-06 | fix | Loop Engineering V6鍏ㄩ潰娴嬭瘯82椤?8.8%閫氳繃 |
| 2026-07-06 | feat | 鏂囨。鍐呭缂栬緫(TinyMCE瀵屾枃鏈?LLM瀵硅瘽淇敼+鍙屾ā寮? |
| 2026-07-06 | feat | 鍥涘ぇ鏅鸿兘鎺掔増(淇DOC/鑷姩鍖归厤妯℃澘/璋冩暣鍥炲啓/杩唬瀛︿範) |
| 2026-07-06 | feat | 妯℃澘绠＄悊椤?鏍峰紡淇+闄勫綍鏍峰紡鍒嗙 |
| 2026-07-06 | fix | React 19+antd v5鍏煎琛ヤ竵+涓婁紶鏂囦欢鍚嶄慨澶?|
| 2026-07-03 | feat | 澶氳疆瀵硅瘽+涓婁笅鏂囩獥鍙ｇ鐞?鐘舵€佸帇缂╂硶) |
| 2026-07-03 | feat | 瀵硅瘽鎺掔増+妯℃澘涓婁紶鎻愬彇+妯℃澘CRUD |
| 2026-07-03 | feat | MinerU鍘熷DOCX浼樺厛绠＄嚎+鎵归噺涓婁紶+鏍峰紡鎻愬彇鍏ㄩ潰澧炲己 |
| 2026-07-03 | fix | 鍏ㄦ爤娴嬭瘯6涓狟ug淇(Loop Engineering棣栬疆) |

