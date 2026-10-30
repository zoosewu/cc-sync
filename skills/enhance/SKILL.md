---
name: enhance
description: 在任何機器、任何專案裡改進 cc-sync 本身：改碼、驗證、發版、更新本機 plugin
argument-hint: <要改進的內容>
disable-model-invocation: true
---

# 改進 cc-sync

需求：$ARGUMENTS

## 1. 取得 repo
- 目前目錄的 `git remote get-url origin` 是 `zoosewu/cc-sync`（不是 `cc-sync-data`）→ 就在這裡工作。
- 否則用固定位置 `~/.cache/cc-sync-dev`：不存在就 `git clone https://github.com/zoosewu/cc-sync.git ~/.cache/cc-sync-dev`。
- `git pull --rebase`。工作樹有未提交變更 → 停下，列出變更問使用者。

完成條件：repo 在最新的 `main`、工作樹乾淨。

## 2. 讀脈絡
讀 repo 的 `CLAUDE.md`、`docs/spec.md`，以及存在時的 `docs/handoff.md`。之後的工作以 repo 的 `CLAUDE.md` 為準（協作規則、mod 陷阱、public repo 限制）。

## 3. 實作
依需求修改；行為變了就同步更新 `docs/spec.md`，並補對應的 pytest 或 mod 測試。

## 4. 驗證
在 repo 根目錄依序執行，三者全綠才往下：
- `uv run pytest`
- `claude plugin validate .`
- `claude plugin test .`

## 5. 發版
1. `.claude-plugin/plugin.json` 的 `version` patch 加一（`claude plugin update` 依版本判斷有無新版）。
2. 列出變更摘要與 diff stat，徵得同意後 commit、push 到 `main`。

## 6. 更新本機
```
claude plugin marketplace update cc-sync
claude plugin update cc-sync@cc-sync
```
告訴使用者：重啟 Claude Code 生效；其他機器執行同樣兩行再重啟。
