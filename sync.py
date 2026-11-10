import urllib.request, xml.etree.ElementTree as ET, re, json, datetime, subprocess, os

feed_url = 'https://padlet.com/padlets/9bt5kg1ms2i2yy47/exports/feed.xml?token=ec86762432214910bfe2d6054e6a5af0'
print("正在連線至 Padlet 抓取最新聯絡簿...")

req = urllib.request.Request(feed_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
try:
    resp = urllib.request.urlopen(req, timeout=15)
    root = ET.fromstring(resp.read().decode('utf-8'))
except Exception as e:
    print("連線 Padlet 失敗:", e)
    input("按任意鍵結束...")
    exit(1)

items = root.findall('.//item')
date_regex = re.compile(r'^\d{2,4}$|^\d{1,2}/\d{1,2}$')

target_item = None
for item in reversed(items):
    title = (item.find('title').text or '').strip()
    if date_regex.match(title):
        target_item = item
        break

if target_item is not None:
    title = target_item.find('title').text.strip()
    pub_date = target_item.find('pubDate').text.strip()
    desc = target_item.find('description').text or ''
    
    lines = [re.sub(r'<[^>]+>', '', l).strip() for l in re.split(r'</?(?:li|p|br)[^>]*>', desc) if l.strip()]
    tasks = []
    
    # 1. 永遠固定第一項：聯絡簿
    tasks.append({
        'id': 'hw_contact_book',
        'title': '聯絡簿',
        'isFixed': True
    })
    
    for idx, line in enumerate(lines):
        clean = re.sub(r'^[\d\(\)（）\.\、\s]+', '', line).strip()
        if clean and clean != '聯絡簿':
            not_hw = any(k in clean for k in ['穿班服', '考直笛', '明天考', '下週考', '期中考', '放假', '通知單'])
            if not not_hw:
                tasks.append({
                    'id': f'hw_padlet_{idx}_{int(datetime.datetime.now().timestamp())}',
                    'title': clean,
                    'isFixed': False
                })

    data = {
        'postTitle': title,
        'pubDate': pub_date,
        'updatedAt': datetime.datetime.now().isoformat(),
        'homeworkList': tasks
    }
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(script_dir, 'homework.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ 成功抓取最新聯絡簿【{title}】：")
    for t in tasks:
        print(f"  • {t['title']}")
        
    print("\n正在推送至 GitHub Pages...")
    try:
        subprocess.run(["git", "add", "homework.json"], cwd=script_dir, check=True)
        subprocess.run(["git", "commit", "-m", f"chore: sync Padlet {title}"], cwd=script_dir, check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=script_dir, check=True)
        print("🎉 推送完成！GitHub Pages 約 20 秒內自動更新。")
    except Exception as e:
        print("推送 GitHub 時發生錯誤（若未連網可忽略）:", e)
else:
    print("找不到帶有日期的聯絡簿貼文")

input("\n按 Enter 鍵關閉視窗...")
