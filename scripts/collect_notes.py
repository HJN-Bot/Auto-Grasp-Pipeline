#!/usr/bin/env python3
import re, json, html, argparse, tempfile, subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import requests

VENV_PY = '/home/ubuntu/.openclaw/workspace/.venv_stt/bin/python'

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

def get_youtube_transcript(vid: str):
    code = f'''
from youtube_transcript_api import YouTubeTranscriptApi
import json
vid={vid!r}
try:
  data=YouTubeTranscriptApi.get_transcript(vid,languages=['en','zh-Hans','zh-CN'])
  print(json.dumps({{'ok':True,'data':data}},ensure_ascii=False))
except Exception as e:
  print(json.dumps({{'ok':False,'err':type(e).__name__+': '+str(e)}},ensure_ascii=False))
'''
    p = subprocess.run([VENV_PY, '-c', code], capture_output=True, text=True)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None, 'transcript_api_parse_failed'
    if out.get('ok'):
        return out['data'], None
    return None, out.get('err')

def yt_dlp_audio(url: str, out_wav: str):
    with tempfile.TemporaryDirectory() as td:
        cmd = ['yt-dlp', '-f', 'bestaudio', '--no-playlist', '-o', f'{td}/audio.%(ext)s', url]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout)[-700:]
        files = list(Path(td).glob('audio.*'))
        if not files:
            return False, 'audio_not_downloaded'
        src = str(files[0])
        f = subprocess.run(['ffmpeg','-y','-i',src,'-vn','-ac','1','-ar','16000',out_wav], capture_output=True, text=True)
        if f.returncode != 0:
            return False, (f.stderr or f.stdout)[-700:]
    return True, None

def whisper_transcribe(wav_path: str):
    code = f'''
from faster_whisper import WhisperModel
import json
model=WhisperModel('small',device='cpu',compute_type='int8')
segments,info=model.transcribe({wav_path!r}, vad_filter=True)
out=[]
for s in segments:
  out.append({{'start':s.start,'end':s.end,'text':s.text.strip()}})
print(json.dumps({{'ok':True,'language':info.language,'segments':out}},ensure_ascii=False))
'''
    p = subprocess.run([VENV_PY, '-c', code], capture_output=True, text=True)
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception:
        return None, 'whisper_parse_failed'
    return out, None

def fetch_meta(url: str):
    try:
        r = requests.get(url, timeout=20, headers={'User-Agent':'Mozilla/5.0'})
        text = r.text
    except Exception as e:
        return {'error': str(e)}
    title = ''
    m = re.search(r'<title[^>]*>(.*?)</title>', text, re.I|re.S)
    if m: title = html.unescape(re.sub(r'\s+',' ',m.group(1)).strip())
    desc = ''
    for pat in [r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']', r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']']:
        m = re.search(pat, text, re.I|re.S)
        if m:
            desc = html.unescape(re.sub(r'\s+',' ',m.group(1)).strip())
            break
    return {'title': title, 'desc': desc}

def x_oembed(url: str):
    api='https://publish.twitter.com/oembed'
    try:
        r=requests.get(api, params={'url':url}, timeout=20)
        if r.status_code==200:
            j=r.json()
            h=j.get('html','')
            text=re.sub('<[^<]+?>',' ',h)
            text=re.sub(r'\s+',' ',html.unescape(text)).strip()
            return {'ok':True,'text':text}
        return {'ok':False,'error':f'HTTP {r.status_code}'}
    except Exception as e:
        return {'ok':False,'error':str(e)}

def summarize_structured(source, text):
    text = (text or '').strip()
    if not text:
        return {
            'core_claim':'', 'support_points':[], 'quote_zh':'', 'quote_en':'', 'tags':[]
        }
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
        tags += ['YouTube','视频笔记']
    elif 'xiaohongshu' in host or 'xhslink' in host:
        tags += ['小红书','内容拆解']
    elif 'weixin' in host or 'wemp.app' in host:
        tags += ['公众号','长文提炼']
    elif 'twitter' in host or 'x.com' in host:
        tags += ['X','推文拆解']
    tags = tags[:3]
    return {
        'core_claim': core[:120],
        'support_points': [s[:140] for s in supports],
        'quote_zh': quote_zh,
        'quote_en': quote_en,
        'tags': tags,
    }

def assess_quality(item, min_chars=300):
    chars = len((item.get('body') or '').strip())
    title_ok = bool((item.get('title') or '').strip())
    enough = chars >= min_chars
    return {
        'chars': chars,
        'title_ok': title_ok,
        'enough': enough,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('links', nargs='+')
    ap.add_argument('--out', default='/home/ubuntu/.openclaw/workspace/agents/lulu/deliverables/notes/collected_notes.md')
    ap.add_argument('--min-chars', type=int, default=300)
    args=ap.parse_args()

    outp=Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    records=[]
    for u in args.links:
        host=urlparse(u).netloc.lower()
        rec={'url':u,'platform':'web','title':'','body':'','method':'','errors':[]}

        if 'youtu' in host:
            rec['platform']='youtube'
            vid=video_id_from_url(u)
            rec['title']=f'YouTube video {vid or ""}'.strip()
            tr, err = get_youtube_transcript(vid) if vid else (None,'video_id_missing')
            if tr:
                txt=' '.join([x.get('text','') for x in tr])
                rec['body']=txt
                rec['method']='transcript_api'
            else:
                rec['errors'].append(f'transcript_api_fail: {err}')
                wav='/tmp/yt_fallback.wav'
                ok,e=yt_dlp_audio(u,wav)
                if ok:
                    wh,e2=whisper_transcribe(wav)
                    if wh and wh.get('ok'):
                        segs=wh.get('segments',[])
                        rec['body']=' '.join([s.get('text','') for s in segs])
                        rec['method']='yt-dlp+whisper'
                    else:
                        rec['errors'].append(f'whisper_fail: {e2}')
                else:
                    rec['errors'].append(f'yt-dlp_fail: {e}')

        elif 'x.com' in host or 'twitter.com' in host:
            rec['platform']='x'
            o=x_oembed(u)
            if o.get('ok'):
                rec['body']=o.get('text','')
                rec['method']='oembed'
                rec['title']=(rec['body'][:70] + '...') if len(rec['body'])>70 else rec['body']
            else:
                rec['errors'].append(f"oembed_fail: {o.get('error')}")

        else:
            meta=fetch_meta(u)
            rec['platform']='web'
            if 'error' in meta:
                rec['errors'].append(f"fetch_fail: {meta['error']}")
            else:
                rec['title']=meta.get('title','')
                rec['body']=meta.get('desc','')
                rec['method']='web_meta'

        rec['quality']=assess_quality(rec, args.min_chars)
        rec['outline']=summarize_structured(u, rec.get('body',''))
        records.append(rec)

    need_materials=[]
    outlines=[]
    for r in records:
        q=r['quality']
        if q['enough']:
            outlines.append(r)
        else:
            missing=[]
            if not r.get('body','').strip():
                missing.append('正文内容')
            elif q['chars'] < args.min_chars:
                missing.append(f'正文不足{args.min_chars}字（当前{q["chars"]}）')
            provide='复制正文 OR 截图'
            if r['platform'] == 'youtube':
                provide='导出音频文件 OR 视频文件 OR 提供可访问字幕'
            need_materials.append({
                'source': r['url'],
                'got': f"标题「{r.get('title','(无)')}」",
                'missing': '；'.join(missing) if missing else '正文内容',
                'provide': provide,
            })

    lines=['# Collected Notes (auto)', '']
    lines.append('## 抓取结果概览')
    for r in records:
      lines.append(f"- {r['platform']} | method={r.get('method','(none)')} | chars={r['quality']['chars']} | url={r['url']}")
      if r['errors']:
          for e in r['errors']:
              lines.append(f"  - warn: {e}")
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
            o=r['outline']
            lines.append(f"### 来源：{r['url']}")
            lines.append(f"核心主张（1句话）：{o['core_claim'] or '（待补料）'}")
            lines.append('支撑论点（3条以内）：')
            if o['support_points']:
                for p in o['support_points'][:3]:
                    lines.append(f"- {p}")
            else:
                lines.append('- （待补料）')
            lines.append(f"金句/可引用表达（中文1条）：{o['quote_zh'] or '（待补料）'}")
            lines.append(f"金句/可引用表达（英文1条）：{o['quote_en'] or '（待补料）'}")
            lines.append(f"适合发布的标签（3个）：{', '.join(o['tags'][:3]) if o['tags'] else '（待补料）'}")
            lines.append('')

    outp.write_text('\n'.join(lines), encoding='utf-8')
    print(str(outp))

if __name__=='__main__':
    main()
