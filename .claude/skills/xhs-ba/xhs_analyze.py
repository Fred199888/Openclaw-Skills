#!/usr/bin/env python3
"""
小红书博主分析器 - 基于 SSR HTML 数据
解析已获取的完整 HTML，提取帖子信息 + 下载封面图 + 生成夸赞话术
"""
import re
import json
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup


def parse_profile_html(html: str) -> dict:
    """从 SSR HTML 解析博主和帖子数据"""
    soup = BeautifulSoup(html, 'html.parser')

    # 博主名称（从 title）
    blogger_name = ""
    title = soup.find('title')
    if title:
        m = re.match(r'^(.+?)\s*[-–]\s*小红书', title.get_text())
        if m:
            blogger_name = m.group(1).strip()

    # 解析帖子
    posts = []
    feeds = soup.find('div', id='userPostedFeeds')
    if feeds:
        note_items = feeds.find_all('section', class_='note-item')
        for item in note_items:
            # 标题
            title_el = item.find(class_='title')
            title_text = title_el.get_text().strip() if title_el else ''

            # 封面图
            img = item.find('img')
            img_url = (img.get('src') or img.get('data-src') or '') if img else ''

            # 点赞/互动数（在 footer 里找纯数字）
            footer_text = item.get_text()
            numbers = re.findall(r'\n(\d+)\n', footer_text)
            likes = numbers[-1] if numbers else ''

            # 是否置顶
            is_top = bool(item.find(class_='top-wrapper'))

            # data-index
            data_index = item.get('data-index', '0')

            posts.append({
                'index': int(data_index),
                'title': title_text,
                'cover_url': img_url,
                'likes': likes,
                'is_top': is_top,
                'cover_local': '',
            })

    return {
        'blogger_name': blogger_name,
        'posts': posts,
        'total_posts': len(posts),
    }


def download_covers(posts: list, img_dir: Path) -> None:
    """下载封面图"""
    img_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.xiaohongshu.com/',
    })

    for post in posts:
        url = post['cover_url']
        if not url:
            continue
        base_url = url.split('!')[0]
        filename = f"cover_{post['index']:02d}.jpg"
        local_path = img_dir / filename

        if local_path.exists():
            post['cover_local'] = str(local_path)
            continue

        try:
            r = session.get(base_url, timeout=15)
            if r.status_code == 200:
                local_path.write_bytes(r.content)
                post['cover_local'] = str(local_path)
                print(f"  ✅ {filename} ({len(r.content)//1024}KB)")
            else:
                print(f"  ❌ {filename}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  ❌ {filename}: {e}")
        time.sleep(0.5)


def generate_compliments(blogger_name: str, posts: list, blogger_bio: str = '') -> str:
    """
    完全动态的夸赞话术生成器。
    根据博主实际帖子标题自动识别内容主题，所有话术都引用真实帖子，
    不硬编码任何博主特有信息。
    """
    name = blogger_name or '博主'
    titles = [p['title'] for p in posts if p['title']]

    def safe_int(s):
        try: return int(s)
        except: return 0

    top_posts = sorted(posts, key=lambda x: safe_int(x['likes']), reverse=True)[:3]
    # 取点赞最高的帖子标题作为例子引用
    ex1 = top_posts[0]['title'][:18] if top_posts else (titles[0][:18] if titles else '你的帖子')
    ex2 = top_posts[1]['title'][:18] if len(top_posts) > 1 else (titles[1][:18] if len(titles) > 1 else ex1)

    # ---- 动态主题识别 ----
    # 规则：关键词 → (主题名, 匹配的帖子列表)
    TOPIC_RULES = [
        ('穿搭时尚', ['穿', 'ootd', 'outfit', '搭配', '穿搭', '上衣', '裙', '裤', '外套', '衬衫', '毛衣', '卫衣', 'look']),
        ('旅行探险', ['旅', '游', '打卡', '景点', '海边', '岛', '山', '潜水', '泳池', 'summer', '出发', '飞', '机票', '酒店', '民宿', '露营']),
        ('美食餐厅', ['吃', '餐厅', '美食', '下午茶', '甜品', '奶茶', '咖啡', '火锅', '烧烤', '探店', '好吃', '味道']),
        ('美妆护肤', ['口红', '粉底', '护肤', '化妆', '精华', '面膜', '妆', '彩妆', '底妆', '眼影', '防晒', '素颜']),
        ('健身运动', ['健身', '运动', '瑜伽', '跑步', '减脂', '减肥', '练', '体脂', '塑形', '力量']),
        ('读书学习', ['读书', '书单', '学习', '考试', '考研', '备考', '笔记', '知识', '干货', '技能']),
        ('生活美学', ['在家', '拍照', '日常', '生活', '治愈', '温柔', '氛围', '布置', '风格', '慢生活']),
        ('购物种草', ['好物', '种草', '推荐', '购', '买', '折扣', '涨价', '宝藏', '神器', '攻略', '测评', '值得买']),
        ('职场工作', ['工作', '职场', '上班', '打工', '兼职', '实习', '面试', '简历', '升职', '办公']),
        ('母婴育儿', ['宝宝', '孩子', '育儿', '辅食', '早教', '母乳', '怀孕', '备孕', '妈妈']),
        ('宠物', ['猫', '狗', '宠物', '铲屎官', '狗狗', '猫咪', '养猫', '养狗']),
        ('数码科技', ['手机', '电脑', '数码', '科技', '测评', 'iphone', 'mac', '平板']),
    ]

    all_text = ' '.join(titles).lower()
    active_topics = []
    topic_example_map = {}  # 主题 → 该主题的代表帖子标题

    for topic_name, keywords in TOPIC_RULES:
        matched = [p for p in posts if any(kw in p['title'].lower() for kw in keywords)]
        if matched:
            active_topics.append(topic_name)
            topic_example_map[topic_name] = matched[0]['title'][:18]

    if not active_topics:
        active_topics = ['综合生活']

    # ---- 话术生成 ----
    lines = []
    lines.append(f"# 🌟 @{name} 博主夸赞话术大全\n")
    lines.append(f"**分析来源**：{len(posts)} 篇帖子 | **内容方向**：{' | '.join(active_topics[:4])}\n")
    lines.append(f"**代表作品**：{'、'.join(p['title'][:12] for p in top_posts[:3])}\n")
    lines.append("=" * 60)

    compliments = []

    # ---- 维度1：核心内容专长（取第一个识别到的主题，动态生成） ----
    if active_topics:
        main_topic = active_topics[0]
        topic_ex = topic_example_map.get(main_topic, ex1)

        # 主题 → 对应夸赞词语
        TOPIC_PRAISE = {
            '穿搭时尚': ('穿搭审美', '时尚感知力', '穿搭品味'),
            '旅行探险': ('旅行眼光', '探索精神', '生活品味'),
            '美食餐厅': ('美食触觉', '探店眼光', '味觉审美'),
            '美妆护肤': ('美妆技术', '护肤知识', '对美的感知'),
            '健身运动': ('自律精神', '运动热情', '对身体的热爱'),
            '读书学习': ('学习态度', '知识积累', '上进心'),
            '生活美学': ('生活审美', '日常美感', '对生活的热爱'),
            '购物种草': ('选品眼光', '好物嗅觉', '分享精神'),
            '职场工作': ('职场经验', '分享精神', '对工作的热情'),
            '母婴育儿': ('育儿智慧', '对孩子的用心', '妈妈力'),
            '宠物': ('对宠物的爱', '养宠经验', '和动物的缘分'),
            '数码科技': ('科技品味', '数码眼光', '对新事物的敏感'),
            '综合生活': ('生活审美', '内容眼光', '分享能力'),
        }
        praise_words = TOPIC_PRAISE.get(main_topic, ('内容眼光', '审美', '分享能力'))

        compliments.append({
            'title': f'{main_topic}——你的天赋领域',
            'scripts': [
                f"姐！你的{praise_words[0]}真的绝了！每次刷到你的帖子都忍不住停下来细看，那种{praise_words[1]}不是刻意练出来的，是真的刻在骨子里的天赋。就比如你的「{topic_ex}」那篇，别人可能只看到表面，但你的角度就是不一样，让人眼前一亮！",
                f"我认认真真研究了你所有关于{main_topic}的内容，发现你有一种很难得的能力——能把自己的{praise_words[1]}转化成别人能感受到的东西。你不只是在做内容，是在传递一种审美和态度，这才是真正有价值的创作！",
                f"你的{praise_words[0]}在同类博主里真的是顶尖水准，不是我吹，是因为你的内容有一种别人学不来的「{name}感」。像「{topic_ex}」这样的帖子，换别人来做可能只有三分之一的效果，因为差的就是你这份对{main_topic}发自内心的热爱和独到眼光！",
            ]
        })

    # ---- 维度2：第二主题（如有） ----
    if len(active_topics) >= 2:
        second_topic = active_topics[1]
        topic_ex2 = topic_example_map.get(second_topic, ex2)
        TOPIC_ABILITY = {
            '穿搭时尚': '时尚审美', '旅行探险': '探索品味', '美食餐厅': '美食触觉',
            '美妆护肤': '美妆眼光', '健身运动': '运动自律', '读书学习': '学习能力',
            '生活美学': '生活美感', '购物种草': '选品嗅觉', '职场工作': '职场洞察',
            '母婴育儿': '育儿智慧', '宠物': '养宠经验', '数码科技': '数码品味',
            '综合生活': '综合审美',
        }
        ability = TOPIC_ABILITY.get(second_topic, '内容创作力')
        compliments.append({
            'title': f'{second_topic}——意想不到的加分项',
            'scripts': [
                f"除了{active_topics[0]}，你的{second_topic}内容也让我惊喜到了！「{topic_ex2}」这一篇看完真的惊叹，你的{ability}不输任何专业博主，而且你的视角更真实、更有温度，不像那种为了内容而做内容的感觉！",
                f"你是那种很难被贴标签的博主——因为你太全面了！{main_topic}做得好也就算了，连{second_topic}你也这么有一手，「{topic_ex2}」就是最好的证明。这种多维度的能力真的让人佩服，感觉你是真的热爱生活的方方面面！",
                f"关注你之后我才知道，一个人的{active_topics[0]}和{second_topic}可以完美结合，并且两个都做得极好。你不是那种「只会一招」的博主，而是真正把生活经营得丰富精彩的人，「{topic_ex2}」就是你这种多元生活力的最好体现！",
            ]
        })

    # ---- 维度3：镜头感与内容质感（通用，引用真实帖子） ----
    compliments.append({
        'title': '视觉呈现——每一张都是壁纸',
        'scripts': [
            f"你的镜头感真的太有辨识度了！每张封面都有一种「不用修也好看」的质感，构图、光线、情绪全都到位，看到你的封面图就知道这是{name}的帖子。就像「{ex1}」的那张封面，随便截图出来就是大片级别！",
            f"我一直在思考为什么你的图就是比别人看起来高级，后来发现是因为你拍的不是「景」而是「感觉」——你能把当下的情绪通过镜头传递给看的人。这种能力真的不是买滤镜、学后期能弥补的，是你对美天生的敏锐感知！",
            f"你的主页打开来真的是视觉享受，不是那种刻意设计的统一感，而是你的审美自然流露出来的风格一致。每一张图都有温度、有故事，看着看着就忘了时间，这才是真正意义上的「高质量内容」！",
        ]
    })

    # ---- 维度4：真实感与人情味（通用） ----
    compliments.append({
        'title': '真实感——你的最大竞争力',
        'scripts': [
            f"你的内容有一种非常难得的「真实感」——不是那种精心包装的营销腔，是一个真实的人在认真分享自己的生活。像「{ex1}」这篇，就很有你自己的个性和想法在里面，这种真诚感才是最打动人的！",
            f"现在做博主的人越来越多，套路也越来越像，但你一直保持着自己的风格，不跟风不凑热闹。你让我相信做博主可以不焦虑——就是真诚地分享自己觉得好的东西，然后自然地积累真正喜欢你的粉丝，你就是最好的例子！",
            f"你的每一篇帖子都感觉得到你的用心，哪怕是看起来随手分享的「{ex2}」，也能感受到你对内容的态度。这种认真劲儿是真的藏不住的，难怪粉丝越来越多，因为真心换真心，你的用心大家都看到了！",
        ]
    })

    # ---- 维度5：内容价值与影响力（引用互动数） ----
    total_likes = sum(safe_int(p['likes']) for p in posts)
    likes_str = f"{total_likes:,}" if total_likes > 0 else "数千"
    hot_title = top_posts[0]['title'][:15] if top_posts else ex1
    compliments.append({
        'title': '影响力——靠内容赢的口碑',
        'scripts': [
            f"你的获赞和收藏数字证明了一件事：好内容自有人赏识。你从来不靠噱头、不靠买量，就是用实实在在的内容打动人，「{hot_title}」能爆是因为它真的好，这种靠实力赢来的影响力比什么都值钱！",
            f"我身边有好几个朋友都是因为你的帖子才去尝试了新的东西，你的内容真的在影响和改变很多人的生活选择。这种无形的价值才是做博主真正该追求的东西，而你已经做到了，而且做得特别自然！",
            f"作为你的粉丝，我有一种很强烈的感觉：你是那种可以「死忠支持」的博主，因为你的内容从来不糊弄人。每次更新都感觉得到你的诚意和用心，这份认真让人打心底里喜欢你，自然而然地就想给你点赞分享！",
        ]
    })

    # ---- 维度6：坚持创作的精神（通用） ----
    compliments.append({
        'title': '创作精神——越看越佩服',
        'scripts': [
            f"你能坚持做内容这件事本身就很了不起！在「流量越来越难做」的今天，你还是在认认真真地更新、用心地分享，这种对创作的坚持和热爱真的让我很感动。你让我相信做真实的内容是有价值的！",
            f"我注意到你的每一篇帖子都有自己的完整度，不是随随便便拍一张就发，是真的认真对待每次分享。这种对自己作品的标准和要求，就是你能持续吸引人的根本原因，说你是用心在做内容真的一点都不为过！",
            f"你的创作力真的让我佩服——{len(posts)} 篇帖子，每一篇都有自己的特色和质感，没有一篇是为了凑数而发的感觉。你对内容的选择和呈现都有自己的坚持，这种创作精神在现在的互联网上真的是稀缺品！",
        ]
    })

    # ---- 维度7：整体人格魅力（通用，收尾） ----
    compliments.append({
        'title': '人格魅力——关注你是一种享受',
        'scripts': [
            f"关注你之后有一个很深的感受：你是那种「把生活过成自己想要的样子」的人。你的帖子里有你鲜明的个性和对生活的态度，不是为了别人的眼光而活，而是真的在享受属于自己的生活，这是最难学到的魅力！",
            f"你散发出来的那种气质真的很特别——自信但不傲慢，有品味但接地气，有自己想法但从不强加于人。跟着你的内容久了，感觉自己对生活的要求也在悄悄提升，你真的是一个很好的「正面影响力」源头！",
            f"在互联网上很难遇到一个让人觉得「这个人真的很酷」同时又「好真实好亲切」的博主，但你做到了。你的内容里有你完整的人格和生命力，不是一个「内容机器」，而是一个真正有意思的人在做内容，这才是真正意义上的有魅力！",
        ]
    })

    # 格式化输出
    for i, cmp in enumerate(compliments, 1):
        lines.append(f"\n## 夸赞角度 {i}：{cmp['title']}\n")
        for j, script in enumerate(cmp['scripts'], 1):
            lines.append(f"**话术 {i}-{j}：**")
            lines.append(f"> {script}\n")

    lines.append("\n" + "=" * 60)
    lines.append(f"\n**汇总**：共 {len(compliments)} 个夸赞维度，{len(compliments)*3} 条话术")
    lines.append(f"**数据来源**：{name} 小红书主页 | 帖子总数 {len(posts)} 篇 | 内容方向：{' | '.join(active_topics) or '综合'}")

    return '\n'.join(lines)


def main(html_source: str, output_dir: str = "xhs_output"):
    """主入口，html_source 可以是文件路径或 HTML 字符串"""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if html_source.endswith('.html') or html_source.endswith('/'):
        with open(html_source, 'r', encoding='utf-8') as f:
            html = f.read()
    else:
        html = html_source

    print(f"📥 HTML 大小: {len(html):,} 字节")

    # 解析数据
    data = parse_profile_html(html)
    name = data['blogger_name']
    posts = data['posts']

    print(f"👤 博主: {name}")
    print(f"📋 帖子总数: {len(posts)}")
    for p in posts:
        top = '📌' if p['is_top'] else '  '
        print(f"  [{p['index']:02d}] {top} {p['title'][:40]} | 👍 {p['likes']}")

    # 下载封面图
    print(f"\n📸 下载封面图...")
    download_covers(posts, Path(output_dir) / 'images')

    # 生成话术
    print(f"\n✍️ 生成夸赞话术...")
    compliments = generate_compliments(name, posts)

    # 保存
    data_file = Path(output_dir) / 'profile_data.json'
    data['posts'] = posts
    data_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    compliment_file = Path(output_dir) / 'compliments.md'
    compliment_file.write_text(compliments)

    print(f"\n✅ 完成！")
    print(f"  数据: {data_file}")
    print(f"  话术: {compliment_file}")
    print(f"  封面图: {output_dir}/images/")

    return compliments


if __name__ == '__main__':
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else '/tmp/xhs_profile.html'
    out = sys.argv[2] if len(sys.argv) > 2 else 'xhs_output'
    result = main(src, out)
    print("\n" + "=" * 60)
    print(result)
