#!/usr/bin/env python3
import os, re, sys, json, html, argparse, tempfile, subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import requests

# --- 环境配置（通过 .env 或系统环境变量注入，不硬编码）---
VENV_PY = os.environ.get('VENV_PYTHON', sys.executable)
YOUTUBE_COOKIES = os.environ.get('YOUTUBE_COOKIES', '')  # cookies.txt 绝对路径
HTTPS_PROXY = os.environ.get('HTTPS_PROXY', '')          # 住宅代理，格式：http://user:pass@host:port

ZH_HINTS = ['的','了','是','在','和','与','我们','你','他','她','它','这','那']


def is_probably_chinese(s: str) -> bool:
    return any(ch in s for ch in ZH_HINTS) or bool(re.search(r'[\u4e00-\u9fff]', s))


def video_id_from_url(url: str):
    if 'youtu.be/' in url:
        return url.split('youtu.be/')[-1].split('?')[0]
    q = parse_qs(urlparse(url).query)
    if 'v' in q:
        return q['v'][0]
    m = re.search(r'youtube\.com/shorts/([^?&/]+)', url)
    return m.group(1) if m else None


def get_youtube_transcript(vid: str, cookies_file: str = '', proxy: str = ''):
    """
    用 youtube-transcript-api 1.2.x 拉字幕。
    1.2.x API: 实例化传 http_client（带 cookie + 代理的 session），调用 fetch()。
    """
    code = f'''
import json, sys, requests, http.cookiejar
vid = {vid!r}
cookies = {cookies_file!r}
proxy = {proxy!r}
LANGS = ["zh", "zh-Hans", "zh-CN", "zh-TW", "en"]

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    import pkg_resources

    session = requests.Session()
    session.headers.update({{
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }})
    if proxy:
        session.proxies = {{"http": proxy, "https": proxy}}
    if cookies:
        cj = http.cookiejar.MozillaCookieJar(cookies)
        cj.load(ignore_discard=True, ignore_expires=True)
        session.cookies = cj

    data = None
    # 新版 API (>=1.2.x): YouTubeTranscriptApi(http_client=session).fetch()
    # 旧版 API (<0.6):    YouTubeTranscriptApi.get_transcript()（无 cookies 支持）
    try:
        api = YouTubeTranscriptApi(http_client=session)
        raw = api.fetch(vid, languages=LANGS)
        data = [{{"text": s.text, "start": s.start, "duration": s.duration}} for s in raw.snippets]
    except TypeError:
        data = YouTubeTranscriptApi.get_transcript(vid, languages=LANGS)

    print(json.dumps({{"ok": True, "data": data}}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({{"ok": False, "err": type(e).__name__ + ": " + str(e)}}, ensure_ascii=False))
'''
    p = subprocess.run([VENV_PY, '-c', code], capture_output=True, text=True)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None, f'transcript_api_parse_failed | stderr: {p.stderr[-300:]}'
    if out.get('ok'):
        return out['data'], None
    return None, out.get('err')


def yt_dlp_audio(url: str, out_wav: str, cookies_file: str = '', proxy: str = ''):
    """下载最优音频并转换为 16kHz 单声道 WAV，供 Whisper 使用。"""
    with tempfile.TemporaryDirectory() as td:
        base_cmd = ['yt-dlp', '-f', 'bestaudio', '--no-playlist', '--no-check-certificates']
        if cookies_file and Path(cookies_file).is_file():
            base_cmd += ['--cookies', cookies_file]
        if proxy:
            base_cmd += ['--proxy', proxy]
        base_cmd += ['-o', f'{td}/audio.%(ext)s']

        # 三层兜底：依次尝试不同客户端，云端 IP 绕过 bot 检测
        attempts = [
            # 1. iOS 原生客户端（住宅代理 + iOS UA，最有效绕过云端 IP 检测）
            base_cmd + ['--extractor-args', 'youtube:player_client=ios',
                        '--user-agent', 'com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X)'],
            # 2. TV embedded 客户端（不需要登录）
            base_cmd + ['--extractor-args', 'youtube:player_client=tv_embedded'],
            # 3. 默认客户端（最后兜底）
            base_cmd,
        ]

        p = None
        for attempt_cmd in attempts:
            p = subprocess.run(attempt_cmd + [url], capture_output=True, text=True)
            if p.returncode == 0:
                break

        if p.returncode != 0:
            return False, (p.stderr or p.stdout)[-700:]
        files = list(Path(td).glob('audio.*'))
        if not files:
            return False, 'audio_not_downloaded'
        src = str(files[0])
        f = subprocess.run(
            ['ffmpeg', '-y', '-i', src, '-vn', '-ac', '1', '-ar', '16000', out_wav],
            capture_output=True, text=True
        )
        if f.returncode != 0:
            return False, (f.stderr or f.stdout)[-700:]
    return True, None


def whisper_transcribe(wav_path: str):
    code = f'''
from faster_whisper import WhisperModel
import json
model = WhisperModel("small", device="cpu", compute_type="int8")
segments, info = model.transcribe({wav_path!r}, vad_filter=True)
out = []
for s in segments:
    out.append({{"start": s.start, "end": s.end, "text": s.text.strip()}})
print(json.dumps({{"ok": True, "language": info.language, "segments": out}}, ensure_ascii=False))
'''
    p = subprocess.run([VENV_PY, '-c', code], capture_output=True, text=True)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None, 'whisper_parse_failed'
    return out, None


def fetch_meta(url: str):
    try:
        r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
        text = r.text
    except Exception as e:
        return {'error': str(e)}
    title = ''
    m = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
    if m:
        title = html.unescape(re.sub(r'\s+', ' ', m.group(1)).strip())
    desc = ''
    for pat in [
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    ]:
        m = re.search(pat, text, re.I | re.S)
        if m:
            desc = html.unescape(re.sub(r'\s+', ' ', m.group(1)).strip())
            break
    return {'title': title, 'desc': desc}


def x_oembed(url: str):
    api = 'https://publish.twitter.com/oembed'
    try:
        r = requests.get(api, params={'url': url}, timeout=20)
        if r.status_code == 200:
            j = r.json()
            h = j.get('html', '')
            text = re.sub('<[^<]+?>', ' ', h)
            text = re.sub(r'\s+', ' ', html.unescape(text)).strip()
            return {'ok': True, 'text': text}
        return {'ok': False, 'error': f'HTTP {r.status_code}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def summarize_structured(source, text):
    text = (text or '').strip()
    if not text:
        return {'core_claim': '', 'support_points': [], 'quote_zh': '', 'quote_en': '', 'tags': []}
    lines = [x.strip() for x in re.split(r'[\n。!?！？]+', text) if x.strip()]
    core = lines[0] if lines else text[:80]
    supports = []
    for ln in lines[1:]:
        if len(supports) >= 3:
            break
        if len(ln) >= 12:
            supports.append(ln)
    quote_en = ''
    quote_zh = ''
    for ln in lines:
        if not quote_en and re.search(r'[A-Za-z]{3,}', ln):
            quote_en = ln[:120]
        if not quote_zh and is_probably_chinese(ln):
            quote_zh = ln[:80]
    tags = []
    host = urlparse(source).netloc.lower()
    if 'youtube' in host or 'youtu.be' in host:
        tags += ['YouTube', '视频笔记']
    elif 'xiaohongshu' in host or 'xhslink' in host:
        tags += ['小红书', '内容拆解']
    elif 'weixin' in host or 'wemp.app' in host:
        tags += ['公众号', '长文提炼']
    elif 'twitter' in host or 'x.com' in host:
        tags += ['X', '推文拆解']
    return {
        'core_claim': core[:120],
        'support_points': [s[:140] for s in supports],
        'quote_zh': quote_zh,
        'quote_en': quote_en,
        'tags': tags[:3],
    }


def assess_quality(item, min_chars=300):
    chars = len((item.get('body') or '').strip())
    return {
        'chars': chars,
        'title_ok': bool((item.get('title') or '').strip()),
        'enough': chars >= min_chars,
    }


def main():
    ap = argparse.ArgumentParser()
    # 安全入参：通过 JSON 文件传递链接，避免 shell 命令注入
    ap.add_argument('--links-file', help='包含 {"links":[...]} 的 JSON 文件路径（推荐）')
    # 保留位置参数作为兼容，仅供命令行直接调用时使用
    ap.add_argument('links', nargs='*')
    ap.add_argument('--out', default=str(Path.home() / 'collected_notes.md'))
    ap.add_argument('--min-chars', type=int, default=300)
    ap.add_argument('--cookies', default=YOUTUBE_COOKIES, help='YouTube cookies.txt 路径')
    ap.add_argument('--format', choices=['md', 'json'], default='md',
                    help='md=写入文件; json=输出 JSON 到 stdout（供 n8n 直接解析）')
    args = ap.parse_args()

    # 读取链接：优先 --links-file，其次位置参数
    if args.links_file:
        payload = json.loads(Path(args.links_file).read_text(encoding='utf-8'))
        links = payload.get('links', [])
    else:
        links = args.links

    if not links:
        print('ERROR: 未提供任何链接', file=sys.stderr)
        sys.exit(1)

    cookies_file = args.cookies
    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    records = []
    for u in links:
        host = urlparse(u).netloc.lower()
        rec = {'url': u, 'platform': 'web', 'title': '', 'body': '', 'method': '', 'errors': []}

        if 'youtu' in host:
            rec['platform'] = 'youtube'
            vid = video_id_from_url(u)
            rec['title'] = f'YouTube video {vid or ""}'.strip()
            tr, err = get_youtube_transcript(vid, cookies_file, HTTPS_PROXY) if vid else (None, 'video_id_missing')
            if tr:
                rec['body'] = ' '.join([x.get('text', '') for x in tr])
                rec['method'] = 'transcript_api'
            else:
                rec['errors'].append(f'transcript_api_fail: {err}')
                wav = '/tmp/yt_fallback.wav'
                ok, e = yt_dlp_audio(u, wav, cookies_file, HTTPS_PROXY)
                if ok:
                    wh, e2 = whisper_transcribe(wav)
                    if wh and wh.get('ok'):
                        rec['body'] = ' '.join([s.get('text', '') for s in wh.get('segments', [])])
                        rec['method'] = 'yt-dlp+whisper'
                    else:
                        rec['errors'].append(f'whisper_fail: {e2}')
                else:
                    rec['errors'].append(f'yt-dlp_fail: {e}')

        elif 'x.com' in host or 'twitter.com' in host:
            rec['platform'] = 'x'
            o = x_oembed(u)
            if o.get('ok'):
                rec['body'] = o.get('text', '')
                rec['method'] = 'oembed'
                rec['title'] = (rec['body'][:70] + '...') if len(rec['body']) > 70 else rec['body']
            else:
                rec['errors'].append(f"oembed_fail: {o.get('error')}")

        else:
            meta = fetch_meta(u)
            rec['platform'] = 'web'
            if 'error' in meta:
                rec['errors'].append(f"fetch_fail: {meta['error']}")
            else:
                rec['title'] = meta.get('title', '')
                rec['body'] = meta.get('desc', '')
                rec['method'] = 'web_meta'

        rec['quality'] = assess_quality(rec, args.min_chars)
        rec['outline'] = summarize_structured(u, rec.get('body', ''))
        records.append(rec)

    need_materials = []
    outlines = []
    for r in records:
        q = r['quality']
        if q['enough']:
            outlines.append(r)
        else:
            missing = []
            if not r.get('body', '').strip():
                missing.append('正文内容')
            elif q['chars'] < args.min_chars:
                missing.append(f'正文不足{args.min_chars}字（当前{q["chars"]}）')
            provide = '复制正文 OR 截图'
            if r['platform'] == 'youtube':
                provide = '导出音频文件 OR 视频文件 OR 提供可访问字幕'
            # 判断具体失败原因（供 Dashboard 显示）
            errors = r.get('errors', [])
            if any('TranscriptsDisabled' in e or 'Sign in' in e or 'bot' in e.lower() for e in errors):
                fail_reason = 'youtube_blocked'
            elif any('transcript_api_fail' in e for e in errors):
                fail_reason = 'transcript_unavailable'
            elif any('yt-dlp_fail' in e for e in errors):
                fail_reason = 'download_failed'
            elif errors:
                fail_reason = 'fetch_failed'
            else:
                fail_reason = 'content_empty'

            need_materials.append({
                'source': r['url'],
                'got': f"标题「{r.get('title', '(无)')}」",
                'missing': '；'.join(missing) if missing else '正文内容',
                'provide': provide,
                'fail_reason': fail_reason,
                'errors': errors[:3],  # 最多传 3 条错误日志
            })

    lines = ['# Collected Notes (auto)', '']
    lines.append('## 抓取结果概览')
    for r in records:
        lines.append(f"- {r['platform']} | method={r.get('method', '(none)')} | chars={r['quality']['chars']} | url={r['url']}")
        for e in r.get('errors', []):
            lines.append(f'  - warn: {e}')
    lines.append('')

    if need_materials:
        lines.append('## 【需要你补充】')
        for m in need_materials:
            lines.append(f"- 来源：{m['source']}")
            lines.append(f"- 已抓到：{m['got']}")
            lines.append(f"- 缺失：{m['missing']}")
            lines.append(f"- 请提供：{m['provide']}")
            lines.append('')

    if outlines:
        lines.append('## 笔记大纲（中英双语结构）')
        for r in outlines:
            o = r['outline']
            lines.append(f"### 来源：{r['url']}")
            lines.append(f"核心主张（1句话）：{o['core_claim'] or '（待补料）'}")
            lines.append('支撑论点（3条以内）：')
            for p in (o['support_points'] or ['（待补料）'])[:3]:
                lines.append(f'- {p}')
            lines.append(f"金句/可引用表达（中文1条）：{o['quote_zh'] or '（待补料）'}")
            lines.append(f"金句/可引用表达（英文1条）：{o['quote_en'] or '（待补料）'}")
            lines.append(f"适合发布的标签（3个）：{', '.join(o['tags'][:3]) if o['tags'] else '（待补料）'}")
            lines.append('')

    if args.format == 'json':
        # JSON 模式：直接输出结构化数据到 stdout，供 n8n 解析后传给 Dify
        combined_text = '\n\n'.join(
            f"[{r['platform']}] {r.get('title', '')}\n{r.get('body', '')}"
            for r in records if r.get('body', '').strip()
        )
        print(json.dumps({
            'ok': True,
            'records': records,
            'outlines': outlines,
            'need_materials': need_materials,
            'combined_text': combined_text,
            'platforms': list({r['platform'] for r in records}),
        }, ensure_ascii=False))
    else:
        # MD 模式：写入 markdown 文件，打印文件路径
        outp.write_text('\n'.join(lines), encoding='utf-8')
        print(str(outp))


if __name__ == '__main__':
    main()
