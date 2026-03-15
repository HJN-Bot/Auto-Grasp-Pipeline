#!/usr/bin/env python3
"""
proxy_probe.py — YouTube 代理可用性判定实验
用法：
  python proxy_probe.py --video <youtube_url> [--proxy <proxy_url>] [--cookies <cookies.txt>]
  python proxy_probe.py --video <youtube_url> --no-proxy   # 对照组：不走代理

结论输出：
  PASS     - 拿到字幕，代理+cookies 组合可用
  BLOCKED  - Sign in to confirm / bot check，代理出口被 YouTube 标记
  NO_CAPTIONS - 视频本身无字幕（非代理问题）
  AUTH_FAIL   - cookies 失效或代理认证失败
"""
import os, sys, json, argparse, subprocess, http.cookiejar
import requests
from urllib.parse import urlparse, parse_qs


def video_id(url: str):
    if 'youtu.be/' in url:
        return url.split('youtu.be/')[-1].split('?')[0]
    q = parse_qs(urlparse(url).query)
    if 'v' in q:
        return q['v'][0]
    import re
    m = re.search(r'youtube\.com/shorts/([^?&/]+)', url)
    return m.group(1) if m else None


def probe_transcript_api(vid: str, proxy: str, cookies: str) -> dict:
    """用 youtube-transcript-api 探测，返回结构化结论。"""
    code = f'''
import json, requests, http.cookiejar
vid = {vid!r}
proxy = {proxy!r}
cookies = {cookies!r}
LANGS = ["zh", "zh-Hans", "zh-CN", "zh-TW", "en", "en-US"]

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    session = requests.Session()
    session.headers.update({{
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }})
    if proxy:
        session.proxies = {{"http": proxy, "https": proxy}}
    if cookies:
        import pathlib
        if pathlib.Path(cookies).is_file():
            cj = http.cookiejar.MozillaCookieJar(cookies)
            cj.load(ignore_discard=True, ignore_expires=True)
            session.cookies = cj
    try:
        api = YouTubeTranscriptApi(http_client=session)
        raw = api.fetch(vid, languages=LANGS)
        data = [s.text for s in raw.snippets]
        print(json.dumps({{"verdict": "PASS", "chars": sum(len(t) for t in data), "preview": " ".join(data[:3])}}))
    except TypeError:
        data = YouTubeTranscriptApi.get_transcript(vid, languages=LANGS)
        print(json.dumps({{"verdict": "PASS", "chars": sum(len(t["text"]) for t in data), "preview": " ".join(t["text"] for t in data[:3])}}))
except Exception as e:
    err = str(e)
    if "sign in" in err.lower() or "confirm" in err.lower() or "bot" in err.lower():
        verdict = "BLOCKED"
    elif "transcriptsdisabled" in err.lower() or "notranscript" in err.lower():
        verdict = "NO_CAPTIONS"
    elif "403" in err or "401" in err or "auth" in err.lower():
        verdict = "AUTH_FAIL"
    else:
        verdict = "ERROR"
    print(json.dumps({{"verdict": verdict, "error": err[:300]}}))
'''
    venv_py = os.environ.get('VENV_PYTHON', sys.executable)
    p = subprocess.run([venv_py, '-c', code], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return {'verdict': 'PARSE_ERROR', 'raw': p.stdout[-200:], 'stderr': p.stderr[-200:]}


def probe_yt_dlp(url: str, proxy: str, cookies: str) -> dict:
    """用 yt-dlp 只获取元数据（不下载），判断是否被 bot check 拦截。"""
    cmd = ['yt-dlp', '--no-playlist', '--skip-download',
           '--print', '%(title)s|||%(duration)s', '--no-warnings']
    if proxy:
        cmd += ['--proxy', proxy]
    if cookies and os.path.isfile(cookies):
        cmd += ['--cookies', cookies]
    # 用 iOS client 绕过
    cmd += ['--extractor-args', 'youtube:player_client=ios',
            '--user-agent', 'com.google.ios.youtube/19.29.1 (iPhone16,2; U; CPU iOS 17_5_1 like Mac OS X)']
    cmd += [url]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    out = p.stdout.strip()
    err = p.stderr.strip()
    if p.returncode == 0 and '|||' in out:
        parts = out.split('|||')
        return {'verdict': 'PASS', 'title': parts[0], 'duration': parts[1]}
    combined = (out + err).lower()
    if 'sign in' in combined or 'confirm' in combined or 'bot' in combined:
        verdict = 'BLOCKED'
    elif '403' in combined or '401' in combined:
        verdict = 'AUTH_FAIL'
    else:
        verdict = 'ERROR'
    return {'verdict': verdict, 'error': (out + '\n' + err)[-300:]}


def run_probe(video_url: str, proxy: str, cookies: str, label: str):
    vid = video_id(video_url)
    if not vid:
        print(f'[{label}] ERROR: 无法解析 video_id')
        return

    print(f'\n{"="*60}')
    print(f'[{label}]')
    print(f'  代理  : {proxy or "(无代理，直连)"}')
    print(f'  视频  : {video_url}')
    print(f'  vid   : {vid}')
    print(f'  cookies: {cookies or "(无)"}')
    print()

    print('  [1/2] youtube-transcript-api ...')
    r1 = probe_transcript_api(vid, proxy, cookies)
    verdict1 = r1.get('verdict', '?')
    print(f'        结论: {verdict1}')
    if verdict1 == 'PASS':
        print(f'        字符数: {r1.get("chars")}  预览: {r1.get("preview","")[:80]}')
    else:
        print(f'        错误: {r1.get("error",r1.get("raw",""))}')

    print('  [2/2] yt-dlp metadata ...')
    r2 = probe_yt_dlp(video_url, proxy, cookies)
    verdict2 = r2.get('verdict', '?')
    print(f'        结论: {verdict2}')
    if verdict2 == 'PASS':
        print(f'        标题: {r2.get("title")}  时长: {r2.get("duration")}s')
    else:
        print(f'        错误: {r2.get("error","")[:200]}')

    # 综合判断
    if verdict1 == 'PASS' or verdict2 == 'PASS':
        final = '✅ 可用'
    elif verdict1 == 'NO_CAPTIONS':
        final = '⚠️  视频无字幕（换一条测试视频）'
    elif verdict1 == 'BLOCKED' or verdict2 == 'BLOCKED':
        final = '❌ 被 YouTube 风控拦截（代理出口 IP 质量问题）'
    elif verdict1 == 'AUTH_FAIL' or verdict2 == 'AUTH_FAIL':
        final = '❌ 认证失败（cookies 过期 或 代理账密错误）'
    else:
        final = f'❓ 未知（transcript={verdict1}, ytdlp={verdict2}）'

    print(f'\n  ★ 综合结论: {final}')
    return {'transcript': verdict1, 'ytdlp': verdict2, 'final': final}


def main():
    ap = argparse.ArgumentParser(description='YouTube 代理可用性探针')
    ap.add_argument('--video', required=True, help='测试用 YouTube URL')
    ap.add_argument('--proxy', default=os.environ.get('HTTPS_PROXY', ''),
                    help='代理 URL，如 http://user:pass@host:port')
    ap.add_argument('--proxy2', default='', help='第二个代理出口（对比测试）')
    ap.add_argument('--cookies', default=os.environ.get('YOUTUBE_COOKIES', ''),
                    help='cookies.txt 路径')
    ap.add_argument('--no-proxy', action='store_true', help='对照组：强制不走代理')
    args = ap.parse_args()

    results = []

    if args.no_proxy:
        r = run_probe(args.video, '', args.cookies, '对照组（直连）')
        results.append(('direct', r))
    else:
        if args.proxy:
            r = run_probe(args.video, args.proxy, args.cookies, '代理1')
            results.append(('proxy1', r))
        if args.proxy2:
            r = run_probe(args.video, args.proxy2, args.cookies, '代理2')
            results.append(('proxy2', r))
        if not args.proxy and not args.proxy2:
            print('未指定代理，用 --proxy 或设置 HTTPS_PROXY 环境变量')
            print('或用 --no-proxy 测试直连对照组')
            sys.exit(1)

    print(f'\n{"="*60}')
    print('【汇总】')
    for label, r in results:
        if r:
            print(f'  {label}: {r.get("final","?")}')

    print('\n【下一步建议】')
    blocked = [l for l, r in results if r and 'BLOCKED' in (r.get('transcript','') + r.get('ytdlp',''))]
    passed  = [l for l, r in results if r and r.get('transcript') == 'PASS' or (r and r.get('ytdlp') == 'PASS')]
    if passed:
        print('  ✅ 至少一个出口可用，可直接使用。')
    elif blocked:
        print('  ❌ 当前代理出口被 YouTube 标记。建议：')
        print('     1. 在 Webshare 后台切换到不同地区的住宅 IP')
        print('     2. 或升级到 sticky session（同一 IP 保持连接）')
        print('     3. 或使用 --proxy2 测试第二个出口')
    else:
        print('  ❓ 请检查 cookies 路径和代理账密是否正确。')


if __name__ == '__main__':
    main()
