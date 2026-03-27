---
name: xhs-ba
description: |
  小红书博主内容分析 + 夸赞话术生成器。给定博主链接，自动爬取帖子信息并生成个性化夸赞话术。

  **支持的 URL 格式：**
  - App 分享短链：https://xhslink.com/m/xxxxx（带文字+URL 的分享内容也可以）
  - Web 完整 URL：https://www.xiaohongshu.com/user/profile/xxxxxxxxxxxx
  - 纯用户 ID（24位hex）：5a56bb34e8ac2b0332ab5f0a

  **输出内容：**
  - 博主基本信息（名称、帖子数、内容方向）
  - 所有帖子列表（标题、封面图）
  - 7 个维度 × 3 条 = 21 条个性化夸赞话术
  - 封面图下载到本地（尽力而为）

  **触发场景：**
  - 用户提供小红书博主链接，需要生成夸赞/拍马屁话术
  - 用户说"帮我分析这个小红书博主"、"生成夸他的话"
  - 执行 /xhs-ba 命令
---

# xhs-ba

## 重要说明

小红书有反爬机制，帖子详情页需要登录才能访问。本 skill 从博主**主页 SSR 数据**提取信息（无需登录），可获得：
- 所有帖子标题（通常 20 篇以内全部获取）
- 封面缩略图
- 互动数据（点赞/收藏）
- 博主 bio 信息

**不能获取**：帖子正文文字、完整图集（需要登录）

## 执行流程

### Step 1：解析 URL，提取用户 ID

接收用户输入（可能是短链、完整 URL 或 ID）：

```python
import re, urllib.request

def resolve_uid(input_url):
    """从各种格式解析出用户 ID"""
    # 直接是 24位 hex ID
    if re.match(r'^[a-f0-9]{24}$', input_url.strip()):
        return input_url.strip()

    # web 完整 URL
    m = re.search(r'xiaohongshu\.com/user/profile/([a-f0-9]{24})', input_url)
    if m:
        return m.group(1)

    # 如果输入包含文字（APP分享格式），提取 URL 部分
    url_match = re.search(r'https?://[^\s，。！\n]+', input_url)
    if url_match:
        url = url_match.group(0)
        # 先检查是否是 web URL
        m2 = re.search(r'xiaohongshu\.com/user/profile/([a-f0-9]{24})', url)
        if m2:
            return m2.group(1)
        # 短链 - 跟随重定向
        if 'xhslink.com' in url:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    final_url = resp.url
                m3 = re.search(r'xiaohongshu\.com/user/profile/([a-f0-9]{24})', final_url)
                if m3:
                    return m3.group(1)
            except Exception as e:
                print(f"短链解析失败: {e}")

    raise ValueError(f"无法从输入解析用户ID: {input_url}")
```

### Step 2：获取博主主页完整 HTML

小红书使用 SSR 渲染，初次加载时服务器会返回包含所有帖子数据的 HTML（通常 300-600KB）。需要用浏览器级别的 headers 请求：

```python
import requests

def fetch_profile_html(uid):
    """获取博主主页完整 SSR HTML"""
    profile_url = f"https://www.xiaohongshu.com/user/profile/{uid}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Cache-Control': 'max-age=0',
    }

    resp = requests.get(profile_url, headers=headers, timeout=20)
    html = resp.text

    # 验证获取到了完整 SSR HTML
    if len(html) < 100000 or 'userPostedFeeds' not in html:
        # 降级：使用 Playwright
        return fetch_with_playwright(profile_url)

    return html

def fetch_with_playwright(profile_url):
    """Playwright 降级方案（可能触发安全验证）"""
    from playwright.sync_api import sync_playwright
    import time

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900},
            locale='zh-CN',
        )
        ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page = ctx.new_page()

        # 捕获原始 HTML 响应
        raw_html = []
        def on_response(resp):
            if profile_url.split('?')[0] in resp.url and resp.status == 200:
                try:
                    body = resp.text()
                    if len(body) > 100000:
                        raw_html.append(body)
                except:
                    pass
        page.on('response', on_response)

        page.goto(profile_url, wait_until='networkidle', timeout=30000)
        time.sleep(3)
        browser.close()

    return raw_html[0] if raw_html else ''
```

**注意**：如果遇到安全验证（显示"请使用小红书APP扫码验证"），说明 IP 已被临时限制。等待一段时间后重试，或提供用户的 Cookie。

### Step 3：解析 HTML，提取帖子数据

```python
from bs4 import BeautifulSoup
import re

def parse_posts(html):
    """从 SSR HTML 解析帖子列表"""
    soup = BeautifulSoup(html, 'html.parser')

    # 博主名称
    blogger_name = ''
    title_tag = soup.find('title')
    if title_tag:
        m = re.match(r'^(.+?)\s*[-–]\s*小红书', title_tag.get_text())
        if m:
            blogger_name = m.group(1).strip()

    # 帖子列表（在 #userPostedFeeds 中）
    posts = []
    feeds = soup.find('div', id='userPostedFeeds')
    if feeds:
        for i, item in enumerate(feeds.find_all('section', class_='note-item')):
            # 标题
            title_el = item.find(class_='title')
            title = title_el.get_text().strip() if title_el else ''

            # 封面图
            img = item.find('img')
            cover_url = (img.get('src') or img.get('data-src') or '') if img else ''

            # 是否置顶
            is_top = bool(item.find(class_='top-wrapper'))

            posts.append({
                'index': int(item.get('data-index', i)),
                'title': title,
                'cover_url': cover_url,
                'is_top': is_top,
            })

    return blogger_name, posts
```

### Step 4：下载封面图（尽力而为）

```python
import requests, time
from pathlib import Path

def download_covers(posts, save_dir):
    """下载封面缩略图"""
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.xiaohongshu.com/',
    })

    for post in posts:
        if not post['cover_url']:
            continue
        base_url = post['cover_url'].split('!')[0]  # 去掉图片处理参数
        filename = f"cover_{post['index']:02d}.jpg"
        save_path = Path(save_dir) / filename

        if save_path.exists():
            post['cover_local'] = str(save_path)
            continue

        try:
            r = session.get(base_url, timeout=15)
            if r.status_code == 200:
                save_path.write_bytes(r.content)
                post['cover_local'] = str(save_path)
                print(f"  ✅ 下载 {filename} ({len(r.content)//1024}KB)")
        except Exception as e:
            print(f"  ⚠️ 跳过 {filename}: {e}")
        time.sleep(0.3)  # 礼貌延迟
```

### Step 5：分析内容主题

根据帖子标题识别博主的主要内容方向：

```python
def analyze_topics(titles):
    """从帖子标题分析内容主题"""
    all_text = ' '.join(titles).lower()

    topic_rules = {
        '穿搭时尚': ['穿', 'ootd', 'outfit', 'hollister', 'hco', '搭配', '穿搭', '上衣', '裙', '裤'],
        '旅行探险': ['潜水', '泳池', '南半球', '童话', 'summer', '旅', '游', '海', '岛'],
        '生活美学': ['在家', '拍照', '风吹', '冬天', '秋天', '🖤', '🌊', '日常'],
        '购物种草': ['lv', 'sa说', '涨价', '宝藏', '攻略', '兼职', '品牌', '好物'],
        '美食餐厅': ['吃', '餐厅', '美食', '下午茶', '甜品', '奶茶'],
        '美妆护肤': ['口红', '粉底', '护肤', '化妆', '精华', '面膜'],
        '健身运动': ['健身', '运动', '瑜伽', '跑步', '减脂'],
    }

    active = [topic for topic, keywords in topic_rules.items()
              if any(kw in all_text for kw in keywords)]

    return active or ['综合生活分享']
```

### Step 6：生成夸赞话术

基于博主内容主题、帖子风格、个人特质生成个性化话术：

**7 个夸赞维度（固定）：**
1. 穿搭/时尚审美（如有相关内容）
2. 旅行/探索品味（如有相关内容）
3. 镜头感与拍照美学（通用）
4. 内容真实有温度（通用）
5. 影响力与口碑（通用）
6. 个人特质/反差萌（根据 bio，如理工女、法律人等）
7. 整体人格魅力（通用）

每个维度生成 3 条不同风格的话术（热情款、细腻款、走心款）。

话术生成要点：
- 引用具体帖子标题，让话术更有针对性
- 语气自然，像真实粉丝说话，不像营销文案
- 涵盖博主的具体内容（如「Hollister 兼职攻略」→ 夸她分享信息的用心）
- 3 条话术风格各异：1 条直接热情、1 条细腻分析、1 条深情走心

**示例话术模板（穿搭维度）：**
```
姐！你的穿搭审美真的绝了！每次刷到你的帖子都觉得自己懂了什么叫「时髦」，
那种随意又好看的气质真的不是谁都能驾驭的。就比如你的「{热门穿搭帖}」那篇，
既有自己的风格又非常好学，你天生就是穿衣界的天花板！
```

### Step 7：输出结果

1. **打印博主信息摘要**（帖子数、主题方向、热门帖子）
2. **列出所有帖子**（序号、标题、是否置顶）
3. **输出完整话术**（7 维度 × 3 条）
4. **保存文件**：
   - `xhs_{uid}/profile_data.json` — 结构化数据
   - `xhs_{uid}/compliments.md` — 话术文档
   - `xhs_{uid}/images/cover_*.jpg` — 封面图

## 安装依赖

```bash
pip install playwright beautifulsoup4 requests
python -m playwright install chromium
```

## 常见问题

**Q: 获取的 HTML 不完整（帖子为 0）？**
A: 小红书可能对当前 IP 做了限制，返回简化页面。解决方案：
   1. 等待 30 分钟后重试
   2. 用户提供 Cookie：将浏览器中的 `xhs-pc-session` 等 Cookie 提供给脚本

**Q: 帖子互动数（点赞/收藏）显示为空？**
A: 点赞数在 SSR HTML 中的格式不稳定，属于正常现象。标题和封面图是主要分析数据。

**Q: 图片下载 403？**
A: CDN URL 有时效性，建议在获取 HTML 后立即下载。也可用 Playwright 访问主页后，图片有浏览器 Cookie 支持就可以下载。

## 完整脚本位置

参考实现：`~/Desktop/workspace/小红书blog/xhs_analyze.py`（已经调试验证可用）
