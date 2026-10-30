# cc-sync spec（草案，待核准）

## 目標
多台機器（W1、W2 Windows；L WSL container；未來 macOS）的 Claude Code 使用者設定自動雙向同步：
新增與刪除都會傳播；不需手動操作。所有腳本走 uv。

## 兩個 repo
| repo | 內容 | 可見度 |
|---|---|---|
| `zoosewu/cc-sync` | 工具本體：Python 套件（`cc-sync` CLI）＋ plugin marketplace（`cc-sync`、`cc-statusline` 兩個 plugin）＋ 測試 | public |
| `zoosewu/cc-sync-data` | 同步資料；工作目錄就是 `~/.claude`（尊重 `CLAUDE_CONFIG_DIR`） | private |

### cc-sync-data 內容（白名單 `.gitignore`：`/*` 全忽略後逐項放行）
- `shared/{plugins,marketplaces,preferences}/<key>.json`：settings.json 的可同步子集，一項一檔（逐行合併 JSON 可能合出缺逗號的壞檔，一項一檔讓 git 以檔案為單位合併、刪除即刪檔）
- `sync-config.json`：共用規則（local-only 樣式、刪除煞車門檻、偏好 key 白名單）
- `CLAUDE.md`、`skills/`（排除 `skills/synced/`）、`agents/`、`commands/`
- `os/linux.md`、`os/windows.md`、`os/macos.md`：OS 專屬指示（見「OS 專屬內容」）
- 單機例外寫在各機 `.git/info/exclude`（不同步）

## OS 專屬內容
CC 無 user 層 settings.local.json、skill 無 OS 條件欄位，故由 cc-sync apply 處理：
- **指示**：apply 把當前 OS 的 `os/<os>.md` 複製為 `~/.claude/rules/cc-sync-os.md`（git 忽略；`~/.claude/rules/` 原生自動載入）
- **skill**：SKILL.md frontmatter 寫 `metadata: { os: [linux, macos] }`（官方定義 metadata 供自有工具使用、CC 忽略）；
  apply 對不符當前 OS 的 skill 在本機 settings.json 寫 `skillOverrides.<name> = "off"`，符合則移除該項
- `skillOverrides` 屬本機 key；cc-sync 只增刪自己依 metadata.os 產生的項目，不碰使用者手設的

## settings.json 的處理
| 類別 | key | 規則 |
|---|---|---|
| 集合 | `enabledPlugins`、`extraKnownMarketplaces` | 雙向同步；排除 local-only 樣式 |
| 偏好 | `language`、`model`、`theme`、`tui`、`editorMode`、`alwaysThinkingEnabled`、`autoMemoryEnabled`、`autoUpdatesChannel` | 雙向同步（清單在 sync-config.json，可調） |
| 受管 | `skillOverrides` | 僅增刪 cc-sync 依 metadata.os 產生的項目 |
| 本機 | `hooks`（herdr 自裝）、`autoMode`、`statusLine`、`skipDangerousModePermissionPrompt`、其他未列 key | 永不碰 |

local-only plugin 樣式（初值）：`*-lsp@*`、`herdr-claude-restart@*`、`cc-sync@*`（自身由 bootstrap 管）。

## 同步循環（`cc-sync sync`）
1. **export**：本機 settings.json → `shared/`；檔案類本來就在 git 工作樹
2. `git add -A` → 有差異才 commit（訊息含主機名）
3. `git pull --rebase`；衝突 → `rebase --abort`，保留本機 commit，status 列警告，不自動解
4. **apply**：比對 pull 前後 `shared/` 的差異（只看 repo 變化，不看本機缺什麼）
   - 新增 → `claude plugin install` / `marketplace add`；移除 → `uninstall` / `marketplace remove`；值變 false → `disable`
   - 偏好 key → 寫回 settings.json
5. `git push`；失敗 → status 警告，下次再推
- 互斥：`~/.claude/.cc-sync.lock`，拿不到就略過本次
- 全程 `GIT_TERMINAL_PROMPT=0`，不卡互動認證

## 觸發點（cc-sync mod）
| 事件 | 動作 |
|---|---|
| `session.start` | 完整循環；結束後 `cc-sync update` 自我更新（marketplace update → `claude plugin update`），有新版 toast 提示重啟 |
| `turn.complete`（僅主 agent） | 完整循環（背景執行，不擋 UI） |
| `session.end` | 不跑 git：整條鏈只有很短的時間預算，逾時被殺在 `git add` 中途會留下 index.lock；殘留變更由下次 `session.start` 補 commit |
| `/sync` | `status`／`now`／`confirm`（解除刪除煞車）／`update`（立即自我更新） |

apply 有 plugin 變動（`needs_restart`）或自我更新升了版 → toast 提示手動重啟；cc-sync 不自動重啟。
自我更新只在 session.start（每回合都連網太頻繁）；版本以 `plugin.json` 的 `version` 判斷，發版必須升版號。

## 刪除安全
- **bootstrap（加入）採聯集**：`~/.claude/.git` 不存在即視為加入；只增不刪；同路徑檔案衝突以 repo 為準，本機版本備份到 `~/.claude/.cc-sync-backup/<時間>/`；偏好 key 以 repo 為準
- **刪除煞車**：單次 export 會移除超過 3 項或 ≥50% 的 plugin／檔案 → 不 commit，toast 等 `/sync confirm`
- git 歷史即備份

## Bootstrap
`uvx --from git+https://github.com/zoosewu/cc-sync cc-sync bootstrap <cc-sync-data 的 git URL>`
→ init/fetch → 首台（remote 為空）播種；其他台聯集加入 → `marketplace add zoosewu/cc-sync` + `install cc-sync` → apply
播種順序：W1（plugin 最完整）→ W2 → L。W2、L 加入後自動補裝 mattpocock-skills、commit-commands、context7。

## cc-statusline（獨立 plugin，同 marketplace，經 enabledPlugins 同步）
以 mod 實作，畫在 `AbovePrompt`；取代各機 statusline.ps1／.sh（mod 穩定後各機移除 `statusLine` 與舊腳本）。
| 項目 | 來源 |
|---|---|
| context % | `$.session.usage().context` |
| 5h／7d 用量與重置時間 | `$.session.usage().rateLimits`（不再讀 token、不打 OAuth API） |
| session 時長 | `startedAt` |
| 費用 | `cost` |
| effort | 回合事件的實際 effort |
| 模型名 | 實作時確認來源 |
| git 分支／dirty | `$.process.run`，僅 `turn.complete` 與切換目錄時更新並快取 |
| cc-sync 狀態 | 例 `⟳ 2m`、`⚠ push failed` |
- 更新：`session.measure` 推送觸發重繪，不輪詢、不啟動程序
- 版面沿用現有：第 1 行 模型│context%│目錄(分支*)│時長│effort；空行後 current／weekly 用量條；配色與符號照舊

## 測試
- Python：pytest（export/apply 差異、三方合併、煞車、bootstrap 聯集），以暫存目錄假造 `~/.claude` 與 bare remote
- mod：`claude plugin test`

## 實作時需驗證的未知
1. skills／CLAUDE.md 變更是否免重啟即生效（決定哪些變動要提示重啟）
2. mod 如何取得 plugin 自身目錄（以呼叫 `uv run`）
3. `claude plugin install` 在 session 進行中執行的行為
4. 自我更新後舊版安裝目錄是否立即刪除（會讓本 session 的 mod 在重啟前呼叫不到 CLI）

## 資料遷移（加入時一次性）
- L 的 `CLAUDE.md` 第 4 節「CLI Tools」→ `os/linux.md` 與 `os/macos.md`
- `modern-cli-tools` 改為同步，frontmatter 加 `metadata: { os: [linux, macos] }`

## 開發
- 本機路徑 `D:\Code\Project\cc-sync`
- 實作順序：sync 核心（Python + pytest）→ cc-sync mod → bootstrap 與 W1 播種 → W2／L 加入 → cc-statusline
