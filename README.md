# dsh-guard · DeepSeek Harness 更新后启动弹窗的永久修复

> 作者：[知乎老哥](https://www.zhihu.com/people/svip3)

每次 DSH 自动更新后，启动就弹一个框：

```
DeepSeek Harness 无法使用
应用无法启动或已意外停止。
ENOENT: no such file or directory, open
'E:\DeepSeek\resources\runtime\office-skills\office\SKILL.md'
```

点「重启」还是弹，重装才能活，下一次更新又来一次。

这个仓库给的是**根因 + 自愈守护**，装上之后不用再管。

![崩溃弹窗](docs/crash-dialog.png)

## 为什么会弹

两件事撞在一起：

1. **官方技能包在启动时裸读文件**
   `resources/app.asar` → `dsh/node_modules/@deepseek-ai/dsh-skill-office/lib/index.js`
   的 `apply()` 对 7 个技能名逐个 `readFileSync(join(assetRoot, name, "SKILL.md"))`，没有 try/catch。
   `assetRoot` = `resources/runtime/office-skills`。文件不在 = 抛 ENOENT = 宿主 fatal = 弹框。

2. **安装器在原地覆盖，存在空窗期**
   `%LOCALAPPDATA%\@deepseek-aidsh-desktop-updater\installer-logs\directory-failure-*.log` 里能直接看到：

   ```
   Operation: MoveFileExW
   Windows error: 5 (拒绝访问。)
   Source: e:\DeepSeek
   Destination: e:\DeepSeek.old-{GUID}
   ```

   旧目录改名失败（有进程占着），安装器退化成原地覆盖：先删 `resources/runtime`，再解压。
   如果这段时间应用被拉起（更新完自动启动、或用户手快双击），runtime 还没落盘 → 正好命中 1）。

所以这不是「偶发」，是**每次更新都可能发生**，取决于窗口期里应用有没有起来。

## 怎么修

`dsh_guard.pyw` 常驻（SYSTEM 计划任务），每 0.4 秒做四件事：

| 动作 | 条件 | 结果 |
|---|---|---|
| 补齐技能包 | 任一 `SKILL.md` 缺失 | 0.4 秒内从 stash 复制回去，日志 `heal restored N file(s)` |
| 清理残留 | 主程序没在跑 | 杀掉所有 image path 以 `resources` 所在盘符开头的旧进程，避免安装器再次 error 5 |
| 让路安装器 | 检测到 `installer.exe` / `deepseek-harness-*.exe` | 立即清一遍旧进程（120 秒内只做一次，不会误杀装完新起的实例） |
| 刷新 stash | `app.asar` 大小或 mtime 变化 | 从新版 asar 重新抽取 7 个技能到 stash，升级不丢内容 |

配套：

- `install.ps1`：从注册表找安装位置 → 找 pythonw（优先用 DSH 自带的）→ 复制到 `C:\ProgramData\dsh-guard\` → 备份/抽取 stash → 注册计划任务 `dsh-guard`（SYSTEM / 最高权限 / 开机+登录 / 崩溃自动重启 99 次）。
- `uninstall.ps1`：停任务删任务，`-Purge` 连 `C:\ProgramData\dsh-guard` 一起删。
- `tools\build_stash.py`：不依赖 Electron，直接解析 asar 头（`jlen` + `base=12+json_len+4`），把 7 个技能抽出来；`app.asar.unpacked` 里的项也能处理。

## 安装

管理员 PowerShell：

```powershell
git clone https://github.com/Buir5/dsh-guard.git C:\AI\_scratch\dsh-guard
powershell -ExecutionPolicy Bypass -File C:\AI\_scratch\dsh-guard\install.ps1
```

装完立刻生效，不用重启 DSH。验证：

```powershell
Get-ScheduledTask dsh-guard | Select-Object TaskName,State
Get-Content C:\ProgramData\dsh-guard\guard.log -Tail 20
```

想手动测一次自愈：把 `resources\runtime\office-skills` 改名，两秒内会被补回来。

## 卸载

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
```

## FAQ

**会不会影响更新？** 不会。它只在安装器运行期间清理旧进程，更新照常进行。

**会占多少资源？** 0.4 秒一轮的目录存在性检查，CPU 占用不到 0.1%，内存约 12 MB。

**为什么不用计划任务定时补文件？** 弹窗发生在启动瞬间，分钟级任务来不及；必须常驻轮询。

**卸载后还会弹吗？** 会，等下一次更新窗口期踩中。

---

## English

**Problem.** After every auto-update, DeepSeek Harness dies at boot with
`ENOENT ... resources/runtime/office-skills/office/SKILL.md`, because the bundled
`dsh-skill-office` plugin `readFileSync`s seven SKILL.md files with no error handling,
while the updater wipes `resources/runtime` and re-extracts in place (its
`MoveFileExW` rename fails with Windows error 5 when processes hold the folder).

**Fix.** `dsh_guard.pyw` runs as a SYSTEM scheduled task and polls every 0.4 s:
restores any missing skill file from a local stash, terminates stale processes under the
install root while the app is not running, clears them once when an installer appears,
and refreshes the stash whenever `app.asar` changes.

**Install.** `powershell -ExecutionPolicy Bypass -File install.ps1` (admin).
**Uninstall.** add `-Uninstall`.

MIT License.

---

> **🧭 收徒 · 我靠这套路子吃饭，你也可以**
> 遇到问题先别急着重装，先看日志——九成的「玄学崩溃」都能定位到具体一行。
> 想学这门手艺（逆向、脚本、自动化、把重复劳动交给机器），看这里：
> **[👉 收徒说明（知乎）](https://zhuanlan.zhihu.com/p/54351262)**