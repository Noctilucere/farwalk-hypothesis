# 如何把《远行假设》推到 GitHub

> 现状：代码已在本地 git 仓库（main 分支，3 commits），远程仓库
> `Noctilucere/farwalk-hypothesis` 已在 GitHub 创建（当前为空）。

## 一键推送（网络可访问 GitHub 时）

- **Windows**：双击 `tools\push_github.bat`
- **macOS / Linux / Git Bash**：`sh tools/push_github.sh`

脚本会自动：
1. 添加 remote：`git@github.com:Noctilucere/farwalk-hypothesis.git`
2. `git push -u origin main`

前置条件：
- GitHub SSH key 已配置（本机已有 `~/.ssh/id_ed25519_github`，公钥已添加到 GitHub 账号）
- 网络能访问 GitHub（直连或代理）

## 手动推送（备选）

```bash
git remote add origin git@github.com:Noctilucere/farwalk-hypothesis.git
git push -u origin main
```

## 推送内容

- `README.md`、`run.py`、`build.spec`、`.gitignore`
- `src/`（engine / game / ui / world / data 全部源码）
- `docs/`（架构 / 构建 / GDD / 渲染 / 剧情）
- `tools/`（story_walk 剧情回归 / smoke_test 冒烟测试 / 打包脚本）

> 角色 AI 建模（`assets/models/*.glb`，74 MB）与角色立绘 PNG 体积较大，
> 建议在推送完成后用 GitHub Release 或 Git LFS 补充，避免仓库臃肿。

## 常见问题

| 问题 | 处理 |
|---|---|
| `Permission denied (publickey)` | `ssh -T git@github.com` 测试；确认 `id_ed25519_github.pub` 已加入 GitHub → Settings → SSH keys |
| 443 超时 | 网络未恢复；开代理后 `git config --global http.proxy http://127.0.0.1:<端口>` 再推 |
| 提示没有 main 分支 | `git branch -M main` |
