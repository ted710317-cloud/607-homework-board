import argparse
import datetime
import email.utils
import html
import json
import os
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET

FEED_URL = 'https://padlet.com/padlets/9bt5kg1ms2i2yy47/exports/feed.xml?token=ec86762432214910bfe2d6054e6a5af0'
NON_HOMEWORK_KEYWORDS = (
    '穿班服', '不用帶作業', '考直笛', '明天考', '下週考',
    '期中考', '期末考', '月考', '放假', '通知單'
)


def parse_pub_datetime(pub_str):
    if not pub_str:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(pub_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt
    except Exception:
        return None


def parse_padlet_date_title(title, pub_dt=None):
    """Parse Padlet post titles like '1111', '929', '10/30', '11月11日' into (iso, clean_title)."""
    if not title:
        return None
    clean = title.strip()
    year = pub_dt.year if pub_dt else datetime.datetime.now().year
    pub_month = pub_dt.month if pub_dt else None

    m = d = None
    match = re.match(r'^(\d{1,2})[/.](\d{1,2})(?:$|[^\d])', clean)
    if match:
        m, d = int(match.group(1)), int(match.group(2))
    else:
        match = re.match(r'^(\d{1,2})月(\d{1,2})日?(?:$|[^\d])', clean)
        if match:
            m, d = int(match.group(1)), int(match.group(2))
        else:
            match = re.match(r'^(\d{2})(\d{2})(?:$|[^\d/.\-])', clean)
            if match:
                m, d = int(match.group(1)), int(match.group(2))
            else:
                match = re.match(r'^(\d)(\d{2})(?:$|[^\d/.\-])', clean)
                if match:
                    m, d = int(match.group(1)), int(match.group(2))

    if not m or not d or m < 1 or m > 12 or d < 1 or d > 31:
        return None
    if pub_month == 12 and m == 1:
        year += 1

    try:
        datetime.date(year, m, d)
    except ValueError:
        return None

    return f'{year}-{m:02d}-{d:02d}'


def make_stable_hw_id(iso, title):
    """Generate the same deterministic ID hash as index.html."""
    if title == '聯絡簿':
        return 'hw_contact_book'
    h = 0
    for ch in title:
        code = ord(ch)
        h = ((h << 5) - h + code) & 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    h = abs(h)
    digits = '0123456789abcdefghijklmnopqrstuvwxyz'
    if h == 0:
        b36 = '0'
    else:
        chars = []
        while h:
            chars.append(digits[h % 36])
            h //= 36
        b36 = ''.join(reversed(chars))
    return f"hw_{iso.replace('-', '')}_{b36}"


def clean_task_line(line):
    text = html.unescape(line).replace('\xa0', ' ').strip()
    text = re.sub(r'^(?:[-*•]\s+|\d+\s*[.、)]\s*|\(\d+\)\s*|（\d+）\s*)', '', text)
    return text.strip()


def extract_tasks(description_html, iso):
    clean_desc = re.sub(r'<[^>]+>', '\n', description_html or '')
    tasks = [{
        'id': 'hw_contact_book',
        'title': '聯絡簿',
        'isFixed': True,
    }]
    seen_titles = {'聯絡簿'}
    for raw_line in clean_desc.splitlines():
        clean = clean_task_line(raw_line)
        if not clean or clean in seen_titles:
            continue
        if any(k in clean for k in NON_HOMEWORK_KEYWORDS):
            continue
        seen_titles.add(clean)
        tasks.append({
            'id': make_stable_hw_id(iso, clean),
            'title': clean,
            'isFixed': False,
        })
    return tasks


def main():
    parser = argparse.ArgumentParser(description='同步 Padlet 聯絡簿至 homework.json')
    parser.add_argument('--no-pause', action='store_true', help='完成後不等待按鍵即結束')
    parser.add_argument('--no-push', action='store_true', help='只更新 homework.json，不自動 git push')
    args = parser.parse_args()

    print('正在連線至 Padlet 抓取最新聯絡簿...')
    try:
        req = urllib.request.Request(FEED_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
    except Exception as exc:
        print(f'❌ 連線失敗：{exc}')
        if not args.no_pause:
            input('\n按 Enter 鍵關閉視窗...')
        raise SystemExit(1)

    by_date = {}
    for item in root.findall('.//item'):
        title_el = item.find('title')
        desc_el = item.find('description')
        pub_el = item.find('pubDate')

        title = (title_el.text or '').strip() if title_el is not None else ''
        desc = (desc_el.text or '') if desc_el is not None else ''
        pub_raw = (pub_el.text or '').strip() if pub_el is not None else ''
        pub_dt = parse_pub_datetime(pub_raw)

        iso = parse_padlet_date_title(title, pub_dt)
        if not iso:
            continue

        tasks = extract_tasks(desc, iso)
        pub_str = pub_dt.strftime('%Y-%m-%d %H:%M:%S UTC') if pub_dt else pub_raw
        by_date[iso] = {
            'postTitle': title,
            'pubDate': pub_str,
            'homeworkList': tasks,
        }

    if not by_date:
        print('⚠️ 找不到符合日期格式的聯絡簿貼文（例如 1111、10/30）')
        if not args.no_pause:
            input('\n按 Enter 鍵關閉視窗...')
        raise SystemExit(1)

    latest_iso = sorted(by_date.keys())[-1]
    latest_entry = by_date[latest_iso]

    print(f"✅ 成功抓取！共 {len(by_date)} 筆日期貼文，最新為：「{latest_entry['postTitle']}」（{latest_iso}）")
    for t in latest_entry['homeworkList']:
        if not t.get('isFixed'):
            print(f"   - {t['title']}")

    data = {
        'updatedAt': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'postTitle': latest_entry['postTitle'],
        'date': latest_iso,
        'pubDate': latest_entry['pubDate'],
        'homeworkList': latest_entry['homeworkList'],
        'byDate': by_date,
    }

    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(base_dir, 'homework.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'已更新 {out_path}')

    if not args.no_push:
        print('\n正在推送到 GitHub 同步給網頁版...')
        try:
            subprocess.run(['git', 'add', 'homework.json'], cwd=base_dir, check=True)
            diff_res = subprocess.run(['git', 'diff', '--cached', '--quiet'], cwd=base_dir)
            if diff_res.returncode == 0:
                print('ℹ️ homework.json 沒有變更，略過 commit 與 push。')
            else:
                subprocess.run(['git', 'commit', '-m', f"sync: {latest_entry['postTitle']}"], cwd=base_dir, check=True)
                subprocess.run(['git', 'push', 'origin', 'main'], cwd=base_dir, check=True)
                print('🚀 同步大功告成！網頁版已經變成最新作業囉！')
        except Exception as exc:
            print(f'⚠️ Git 推送過程發生異常：{exc}')

    if not args.no_pause:
        input('\n按 Enter 鍵關閉視窗...')


if __name__ == '__main__':
    main()
