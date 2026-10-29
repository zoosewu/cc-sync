# CLAUDE.md

cc-sync：跨機器（Windows／macOS／Linux）雙向同步 Claude Code 使用者設定。設計見 `docs/spec.md`。
若存在 `docs/handoff.md`（本機、不進 git），開工前先讀它：上一個 session 的進度與待辦。

## 協作
- 一律繁體中文溝通。提問用純文字，不使用 AskUserQuestion 工具。
- Python 一律走 uv（`uv run`、`uvx`）；PATH 上的 `python` 可能是 Windows Store stub。
- 會改動使用者真實 `~/.claude`、或對外（push、建 repo）的步驟，先說明影響再徵求同意。
- 本 repo 是 public：個人機器細節、其他專案名稱、內網位址不得進 commit。

## 結構
- `src/cc_sync/`：Python CLI（`cc-sync bootstrap|sync|status`，輸出一行 JSON）
  - `shared.py` 同步狀態模型（純函式）；`apply.py` 套用變更；`os_content.py` OS 專屬內容；
    `core.py` 同步循環／bootstrap／煞車／鎖；`gitops.py` git 包裝
- `hooks/register.ts`：Claude Code mod（session.start／turn.complete 背景同步、`/sync`）
- repo 根目錄同時是 marketplace（`.claude-plugin/marketplace.json`）與 `cc-sync` plugin
- `tools/`：一次性維運腳本（環境盤點、清理），uv 單檔腳本

## 驗證
- `uv run pytest`（整合測試以 bare repo 模擬多台機器、假 claude CLI）
- `claude plugin validate .` 與 `claude plugin test .`
- mod 型別檢查：tsconfig 依型別檔開頭範本，放在 repo 外，`files` 指向型別檔與 `hooks/register.ts`

## Mod 陷阱
- `$` 只能傳給檔案頂層宣告的函式；傳給 `register` 內的 closure 會被 validate 拒絕。
- `session.end` 整條鏈只有很短的時間預算，不在其中跑 git（被殺會留下 index.lock）。
- `$.plugin.root` 是 plugin.json 所在目錄（此 repo 根目錄），mod 以 `uv run --project` 呼叫 CLI。
