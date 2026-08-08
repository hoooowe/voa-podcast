# Daily English Listening — VOA Learning English → Apple Podcasts

个人英语听力学习工具。输入一篇 VOA Learning English 文章 URL，系统自动提取
英文原文和原始英文音频，调用 LLM 生成中文翻译，生成中英对照静态网页和
Podcast RSS Feed，托管在 GitHub Pages，最终在 Apple Podcasts 中订阅收听。

> **注意**：本项目不生成任何 AI 英文/中文 TTS 音频。Podcast 音频直接使用
> VOA 原始英文 MP3。

---

## 1. 项目介绍

这是一个个人使用的英语听力学习 MVP，目标是把 VOA Learning English 的文章
变成可以在 Apple Podcasts 一边听、一边看英文原文 + 中文翻译的学习材料。

每一期 Episode 包含：

- VOA 原始英文音频（MP3）
- VOA 英文原文
- 中文翻译（LLM 生成）
- 原文链接、来源信息、发布时间、节目标题

**不包含**：用户系统、数据库、Redis、Docker、微服务、移动 App、后台管理。
MVP 尽可能简单：Python + GitHub + GitHub Pages + GitHub Actions。

### 技术栈

- Python 3.12
- requests / BeautifulSoup4（页面抓取与解析）
- Jinja2（静态 HTML 生成）
- PyYAML / python-dotenv（配置）
- 纯 HTML + CSS + 少量 Vanilla JS（前端，无 React/Vue/Node）
- GitHub Actions（自动部署 / 添加 Episode）

---

## 2. 架构图

```text
VOA Learning English
      ↓
输入 VOA URL
      ↓
Python Fetcher (requests + BeautifulSoup)
      ↓
提取：标题 / 发布时间 / 英文正文 / 原始音频 / 来源 URL
      ↓
版权检查 (VOA_ORIGINAL / THIRD_PARTY / UNKNOWN)
      ↓
LLM 中文翻译 (OpenAI-compatible, 段落分批, SHA256 缓存)
      ↓
下载 VOA MP3 → docs/audio/
      ↓
episodes.json (唯一数据源)
      ↓
Jinja2 生成静态 HTML + 生成 feed.xml
      ↓
GitHub Pages (/docs)
      ↓
https://USERNAME.github.io/voa-podcast/
      ↓
Apple Podcasts (RSS 订阅)
```

---

## 3. Python 环境创建

需要 Python 3.12+。macOS 示例：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

> `pip install -e .` 会根据 `pyproject.toml` 把 `src/voa_podcast` 安装为
> 可编辑包，这样脚本和测试都能 `import voa_podcast`。

---

## 4. 配置

### 4.1 LLM 配置

复制环境变量模板并填写你的 OpenAI 兼容 API 信息：

```bash
cp .env.example .env
```

编辑 `.env`：

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-your-key-here
LLM_MODEL=gpt-4o-mini
```

支持任何 OpenAI 兼容接口（OpenAI、DeepSeek、Moonshot、OpenRouter、本地 vLLM 等）。

### 4.2 站点配置

编辑 `config.yaml`，把 `YOUR_USERNAME` 改成你的 GitHub 用户名：

```yaml
site:
  title: "Daily English Listening"
  github_username: "your-username"
  repository: "voa-podcast"
  base_url: "https://your-username.github.io/voa-podcast"
```

**不要**把用户名 / 仓库名 / API Key 写死在 Python 代码里，全部走配置和环境变量。

---

## 5. 添加 Episode

```bash
python scripts/add_episode.py "https://learningenglish.voanews.com/a/your-article/1234567.html"
```

程序会依次：

1. 校验 URL 是否来自 `learningenglish.voanews.com`
2. 抓取并解析页面（标题、发布时间、正文、音频）
3. 版权检查
4. 重复检测（按 `source_url`，辅助按音频 SHA256）
5. 下载英文 MP3
6. 调用 LLM 翻译英文正文（长文章按段落分批，结果按 SHA256 缓存）
7. 写入 `data/episodes.json`
8. 重新生成 HTML 和 `feed.xml`

输出示例：

```text
Episode created successfully

Title:  AI Is Changing Education
Audio:  docs/audio/001-ai-is-changing-education.mp3
Page:   docs/episodes/ai-is-changing-education.html
Podcast Feed: docs/feed.xml
```

### 版权与 `--force`

- `VOA_ORIGINAL`：正常处理
- `THIRD_PARTY`（AP / Reuters / AFP 等）：不处理
- `UNKNOWN`：默认不处理，确认后可手动放行：

```bash
python scripts/add_episode.py "VOA_URL" --force
```

### 重复检测

同一 `source_url` 已存在时会提示 `Episode already exists.` 并退出，避免重复翻译。
音频 SHA256 作为辅助去重。

---

## 6. 本地预览

```bash
python -m http.server 8000 --directory docs
```

访问 <http://localhost:8000> 查看首页，`http://localhost:8000/feed.xml` 查看 RSS。

---

## 7. GitHub Pages 部署

1. 在 GitHub 创建仓库 `voa-podcast`（或你 `config.yaml` 里的名字）。
2. 把代码 push 到 `main` 分支。
3. 仓库 **Settings → Pages**：
   - Source：**Deploy from a branch**
   - Branch：`main`
   - Folder：`/docs`
4. 保存后访问：`https://USERNAME.github.io/voa-podcast/`

> 仓库里也附带 `.github/workflows/deploy-pages.yml`，push 到 `main` 后会自动
> 重建站点并校验 feed，然后通过 GitHub Pages 部署（见第 8 节）。

---

## 8. GitHub Actions 配置

### 8.1 自动部署（deploy-pages.yml）

push 到 `main` 后自动：安装 Python → `pip install` → `build_site.py` →
`validate_feed.py` → 部署 `docs/` 到 GitHub Pages。

### 8.2 通过网页添加 Episode（update-podcast.yml）

在仓库 **Settings → Secrets and variables → Actions** 添加：

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

然后在 **Actions → Update Podcast → Run workflow** 输入 VOA URL 即可。
Action 会自动添加 Episode、commit 并 push，几分钟后 Pages 和 Podcast 自动更新。

这样即使不打开本地电脑，也能在 GitHub 网页上直接添加新一期。

---

## 9. Apple Podcasts 添加 RSS

RSS 地址：

```text
https://USERNAME.github.io/voa-podcast/feed.xml
```

**Mac**：打开 Apple Podcasts → 菜单栏 **File → Follow a Show by URL** → 粘贴上面的 RSS URL。

**iPhone**：在 Apple Podcasts 中通过「通过 URL 关注」粘贴 RSS URL。

订阅后即可看到每一期 Episode，点击播放可听 VOA 原始英文音频，Episode 描述里
能看到英文原文 + 中文翻译 + 原文链接。

> RSS 中包含 `<itunes:block>Yes</itunes:block>`，这是私人学习 Podcast，
> 不会被 Apple Podcast 公共目录主动收录。

---

## 10. 项目限制

- **GitHub Pages 不适合长期保存大量 MP3。** 仓库会随音频增多迅速变大。
  当仓库逐渐变大时，应把音频迁移到 Cloudflare R2 / AWS S3 / 阿里云 OSS /
  GitHub Releases。
  代码已抽象出 `AudioStorage` 接口（`src/voa_podcast/audio_downloader.py`），
  MVP 实现 `GitHubPagesAudioStorage`，未来替换为 `R2AudioStorage` 等即可，
  无需修改 Podcast 核心代码。
- `docs/cover.jpg` 当前是占位图（1x1），Apple Podcasts 建议 1400x1400 以上，
  请替换为自己的封面。
- 翻译质量取决于所选 LLM 模型；英文原文不会被 LLM 修改。
- VOA 页面结构可能变化，解析器设计为多策略（JSON-LD → meta → DOM → fallback），
  集中在 `src/voa_podcast/content_parser.py` 的 `SELECTORS` 中，便于维护。

---

## 11. 项目结构

```text
voa-podcast/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── config.yaml
├── scripts/
│   ├── add_episode.py      # 添加一期 Episode（主流程）
│   ├── build_site.py       # 从 episodes.json 重建站点 + RSS
│   └── validate_feed.py    # 校验 feed.xml 格式
├── src/voa_podcast/
│   ├── config.py            # 配置加载
│   ├── models.py            # 数据模型 (VOAArticle / Episode / ...)
│   ├── voa_fetcher.py       # VOA 页面抓取
│   ├── content_parser.py    # 多策略解析器
│   ├── copyright_checker.py # 版权检查
│   ├── translator.py        # LLM 翻译 + 缓存
│   ├── audio_downloader.py  # MP3 下载 + AudioStorage 抽象
│   ├── episode_repository.py# episodes.json 读写 / 去重 / slug
│   ├── rss_generator.py     # Podcast RSS 生成
│   └── site_generator.py    # Jinja2 静态站点生成
├── data/episodes.json       # 唯一数据源
├── templates/
│   ├── index.html.j2
│   └── episode.html.j2
├── docs/                    # GitHub Pages 根目录
│   ├── index.html
│   ├── feed.xml
│   ├── cover.jpg
│   ├── episodes/*.html
│   └── audio/*.mp3
├── tests/
│   ├── test_parser.py
│   ├── test_rss.py
│   ├── test_repository.py
│   ├── test_site.py
│   ├── test_translator.py
│   ├── test_copyright.py
│   └── fixtures/voa_article.html
└── .github/workflows/
    ├── deploy-pages.yml
    └── update-podcast.yml
```

---

## 12. 运行测试

```bash
source .venv/bin/activate
pytest
```

测试覆盖：VOA HTML 解析、重复检测、RSS XML、RSS enclosure URL、GUID 稳定性、
HTML 生成、翻译缓存、版权检查。单元测试不依赖网络，使用 `tests/fixtures/` 下的
简化 HTML fixture。

---

## 13. 常见问题

**Q: 添加 Episode 报 `LLM_API_KEY is not configured`？**
A: 检查 `.env` 是否存在且变量名正确（GitHub Actions 中检查 Secrets）。

**Q: `Unable to extract VOA article text` / `Unable to locate VOA audio file`？**
A: VOA 页面结构可能变化。打开 `src/voa_podcast/content_parser.py`，在对应的
`SELECTORS` 列表中补充新的 CSS 选择器。解析器会按顺序尝试。

**Q: Apple Podcasts 没有显示 Episode 描述里的中英文？**
A: 描述放在 `<content:encoded>` CDATA 中。确认 `config.yaml` 的 `base_url`
与实际 Pages 地址完全一致，且 `docs/feed.xml` 可公开访问。

**Q: 重新 build 后 GUID 会变吗？**
A: 不会。GUID 形如 `voa-podcast-001`，基于 episode id，永久不变。删除或重建
不会重新生成 GUID。
