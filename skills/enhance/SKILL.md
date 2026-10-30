---
name: enhance
description: 在任何機器、任何專案裡改進 cc-sync 本身：改碼、驗證、發版、更新本機 plugin
argument-hint: <要改進的內容>
disable-model-invocation: true
---

# 改進 cc-sync

需求：$ARGUMENTS

## 1. 取得 repo
- repo 來源：`claude plugin marketplace list --json` 中 `name` 為 `cc-sync` 的項目——`repo` 欄（GitHub `owner/name`）→ `https://github.com/<repo>.git`，`url` 欄則直接用。
- 目前目錄的 `git remote get-url origin` 指向該 repo → 就在這裡工作。
- 否則用固定位置 `~/.cache/cc-sync-dev`：不存在就 clone 該 repo 到這裡。
- `git pull --rebase`。工作樹有未提交變更 → 停下，列出變更問使用者。

完成條件：repo 在最新的 `main`、工作樹乾淨。

## 2. 讀脈絡
讀 repo 的 `CLAUDE.md`、`docs/spec.md`，以及存在時的 `docs/handoff.md`。之後的工作以 repo 的 `CLAUDE.md` 為準（協作規則、mod 陷阱、public repo 限制）。

## 3. 實作
依需求修改；行為變了就同步更新 `docs/spec.md`，並補對應的 pytest 或 mod 測試。

## 4. 驗證
在 repo 根目錄依序執行，全綠才往下：
- `uv run pytest`
- `claude plugin validate .`
- `claude plugin test .`
- 動到 `plugins/<name>/` 時：`claude plugin validate plugins/<name>` 與 `claude plugin test plugins/<name>`

## 5. 發版
1. 改到的每個 plugin，其 `plugin.json` 的 `version` patch 加一（根目錄 `.claude-plugin/` 是 cc-sync、`plugins/<name>/.claude-plugin/` 是其他；`claude plugin update` 依版本判斷有無新版）。
2. 列出變更摘要與 diff stat，徵得同意後 commit、push 到 `main`。

## 6. 更新本機
```
claude plugin marketplace update cc-sync
claude plugin update <改到的 plugin>@cc-sync
```
告訴使用者：重啟 Claude Code 生效；其他機器在下次 session 開始時會自動更新（cc-sync 自我更新涵蓋同 marketplace 的所有已安裝 plugin），再重啟一次即可。
