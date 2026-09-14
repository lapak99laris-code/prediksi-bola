import requests
from bs4 import BeautifulSoup
import csv
import os
import re
import json
import base64
from datetime import datetime, timedelta, timezone

WIB = timezone(timedelta(hours=7))

def get_wib_now():
    return datetime.now(WIB)

BASE_URLS = [
    "https://bolapelangi.jadwalbola.org/prediksi-bola",
    "https://jpbolepalngi.pagesco.de/prediksi-bola"
]
OUTPUT_FOLDER = "hasil_prediksi"
OUTPUT_HTML = "index.html"
LOGOS_CACHE_FILE = "team_logos.json"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ----------------- LOGO MANAGER -----------------
_team_logos = {}

def load_team_logos():
    global _team_logos
    if os.path.exists(LOGOS_CACHE_FILE):
        try:
            with open(LOGOS_CACHE_FILE, 'r', encoding='utf-8') as f:
                _team_logos = json.load(f)
        except Exception:
            _team_logos = {}

def save_team_logos():
    try:
        with open(LOGOS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_team_logos, f, indent=2)
    except Exception:
        pass

def generate_fallback_badge(team_name):
    """Buat badge SVG lingkaran khas emas/oranye dengan inisial tim jika logo tidak ada"""
    clean = re.sub(r'\[.*?\]', '', team_name).strip()
    words = [w for w in re.split(r'[\s\.\-]+', clean) if w]
    if len(words) >= 2:
        initials = (words[0][0] + words[1][0]).upper()
    elif len(words) == 1:
        initials = words[0][:3].upper()
    else:
        initials = "FC"
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"><circle cx="60" cy="60" r="55" fill="#d45e04" stroke="#000" stroke-width="5"/><text x="50%" y="55%" text-anchor="middle" fill="#000" font-size="36" font-weight="bold" font-family="Arial" dy=".3em">{initials}</text></svg>'
    b64 = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{b64}"

def get_team_logo(team_name):
    """Cari logo asli tim dari cache/database 2280+ logo atau TheSportsDB"""
    name_clean = team_name.strip()
    norm = re.sub(r'\[.*?\]|\(.*?\)', '', name_clean).strip()
    
    candidates = [
        norm.lower(),
        name_clean.lower(),
        re.sub(r'\s+(fc|cf|sc|ac|bk|if|afc)\b', '', norm, flags=re.I).strip().lower(),
        re.sub(r'\b(fc|cf|sc|ac|bk|if|afc)\s+', '', norm, flags=re.I).strip().lower(),
        norm.lower().replace('-', ' ').strip(),
        norm.lower().replace('.', '').strip()
    ]
    
    for cand in candidates:
        if cand in _team_logos and _team_logos[cand] and _team_logos[cand].startswith('http'):
            return _team_logos[cand]
        
    # Cari ke API TheSportsDB
    try:
        url = f"https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={requests.utils.quote(norm)}"
        res = requests.get(url, timeout=3).json()
        if res and res.get('teams'):
            badge = res['teams'][0].get('strBadge')
            if badge:
                _team_logos[norm.lower()] = badge
                save_team_logos()
                return badge
    except Exception:
        pass
        
    # Fallback ke badge inisial SVG (tidak disimpan ke cache json agar bisa diganti logo asli kapan saja)
    return generate_fallback_badge(team_name)

# ----------------- PREDIKSI BOLA SCRAPER -----------------
def get_tanggal_prediksi():
    today = get_wib_now()
    tomorrow = today + timedelta(days=1)
    return f"{today.day} - {tomorrow.day} {today.strftime('%B %Y')}"

def cari_link_prediksi():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    today = get_wib_now()
    tomorrow = today + timedelta(days=1)
    target_pattern = rf"{today.day}\s*-\s*{tomorrow.day}"
    print(f"Target pencarian: Prediksi Bola {today.day} - {tomorrow.day} {today.strftime('%B %Y')}")
    
    # Cek semua base URL (utamakan bolapelangi.jadwalbola.org)
    fallback_link = None
    fallback_title = None

    for base_url in BASE_URLS:
        try:
            domain = re.match(r'https?://[^/]+', base_url).group(0)
            resp = requests.get(base_url, headers=headers, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 1. Cari yang persis target hari ini (misal: "10 - 11")
            for a in soup.find_all('a', href=True):
                text = a.get_text(strip=True)
                href = a.get('href', '')
                if 'prediksi-bola' in href.lower() or 'prediksi bola' in text.lower():
                    if re.search(target_pattern, text, re.I) or re.search(target_pattern, href, re.I):
                        full_href = domain + href if href.startswith('/') else href
                        return full_href, text, True
                        
            # Simpan artikel terbaru sebagai cadangan jika hari ini belum rilis
            if not fallback_link:
                for a in soup.find_all('a', href=True):
                    text = a.get_text(strip=True)
                    href = a.get('href', '')
                    if 'prediksi-bola' in href.lower() and any(f"-{x}-" in href for x in range(1, 32)):
                        fallback_link = domain + href if href.startswith('/') else href
                        fallback_title = text
                        break
        except Exception:
            continue
            
    if fallback_link:
        return fallback_link, fallback_title, False
    
    return None, None, False

def hitung_prediksi(tim_home, tim_away, skor):
    try:
        sh, sa = [int(x.strip()) for x in skor.split('-')]
    except:
        sh, sa = 0, 0
        
    diff = sh - sa
    total = sh + sa
    
    if diff > 0:
        p_1x2 = "Home Win (1)"
        note_1x2 = f"{tim_home} Menang"
    elif diff < 0:
        p_1x2 = "Away Win (2)"
        note_1x2 = f"{tim_away} Menang"
    else:
        p_1x2 = "Draw (X)"
        note_1x2 = "Hasil Imbang / Seri"
        
    if diff >= 3:
        p_hdp = f"{tim_home} -2.5"
        note_hdp = "Home Diunggulkan"
        market_line = "HDP -2.5"
    elif diff == 2:
        p_hdp = f"{tim_home} -1.25"
        note_hdp = "Home Unggul"
        market_line = "HDP -1.25"
    elif diff == 1:
        p_hdp = f"{tim_home} -0.5"
        note_hdp = "Performa Home Solid"
        market_line = "HDP -0.5"
    elif diff == 0:
        p_hdp = "0.0 (DNB)"
        note_hdp = "Peluang Sama Kuat"
        market_line = "HDP 0.0"
    elif diff == -1:
        p_hdp = f"{tim_away} -0.5"
        note_hdp = "Performa Away Solid"
        market_line = "HDP -0.5"
    elif diff == -2:
        p_hdp = f"{tim_away} -1.25"
        note_hdp = "Away Diunggulkan"
        market_line = "HDP -1.25"
    else:
        p_hdp = f"{tim_away} -2.5"
        note_hdp = "Away Diunggulkan"
        market_line = "HDP -2.5"
        
    if total >= 4:
        p_ou = f"Over {total - 0.5}"
        note_ou = "Hujan Gol"
    elif total == 3:
        p_ou = "Over 2.5"
        note_ou = "Peluang Gol Terbuka"
    elif total == 2:
        p_ou = "Under 2.5"
        note_ou = "Pertahanan Ketat"
    else:
        p_ou = "Under 1.5"
        note_ou = "Tempo Lambat"
        
    return {
        'hdp': p_hdp, 'note_hdp': note_hdp, 'market_line': market_line,
        'ou': p_ou, 'note_ou': note_ou,
        '1x2': p_1x2, 'note_1x2': note_1x2
    }

def ekstrak_pertandingan_html(html):
    soup = BeautifulSoup(html, 'html.parser')
    matches = []
    
    bulan_map = {
        '01': 'Januari', '02': 'Februari', '03': 'Maret', '04': 'April',
        '05': 'Mei', '06': 'Juni', '07': 'Juli', '08': 'Agustus',
        '09': 'September', '10': 'Oktober', '11': 'November', '12': 'Desember'
    }
    tahun = get_wib_now().year
    
    league_blocks = soup.find_all('section', class_='league-block')
    
    for block in league_blocks:
        h3 = block.find('h3')
        liga = h3.get_text(strip=True) if h3 else "Liga Lainnya"
        
        match_rows = block.find_all('article', class_='match-row')
        for row in match_rows:
            time_el = row.find('div', class_='match-time')
            jam = ""
            tanggal_raw = ""
            if time_el:
                strong = time_el.find('strong')
                if strong:
                    jam = strong.get_text(strip=True)
                span = time_el.find('span')
                if span:
                    span_text = span.get_text(strip=True)
                    tgl_match = re.search(r'(\d{2}/\d{2})', span_text)
                    if tgl_match:
                        tanggal_raw = tgl_match.group(1)
            
            tanggal_formatted = tanggal_raw
            if tanggal_raw and '/' in tanggal_raw:
                try:
                    d, m = tanggal_raw.split('/')
                    tanggal_formatted = f"{int(d)} {bulan_map.get(m, m)} {tahun}"
                except Exception:
                    pass
            
            teams_el = row.find('div', class_='match-teams')
            tim_home = ""
            tim_away = ""
            if teams_el:
                b_tags = teams_el.find_all('b')
                if len(b_tags) >= 2:
                    tim_home = b_tags[0].get_text(strip=True)
                    tim_away = b_tags[1].get_text(strip=True)
                elif len(b_tags) == 1:
                    parts = teams_el.get_text(strip=True).split('VS')
                    tim_home = parts[0].strip()
                    tim_away = parts[1].strip() if len(parts) > 1 else ""
            
            val_el = row.find('div', class_='match-value')
            skor = val_el.get_text(strip=True) if val_el else "0-0"
            
            if tim_home and tim_away:
                matches.append({
                    'liga': liga,
                    'tanggal': tanggal_formatted,
                    'tanggal_raw': tanggal_raw,
                    'jam': jam,
                    'tim_home': tim_home,
                    'tim_away': tim_away,
                    'skor': skor,
                    'pred': hitung_prediksi(tim_home, tim_away, skor)
                })
                
    return matches

def simpan_html(matches, title_text=""):
    if not matches:
        return
        
    leagues_data = {}
    for m in matches:
        liga = m['liga']
        if liga not in leagues_data:
            leagues_data[liga] = []
        leagues_data[liga].append(m)
        
    total_matches = len(matches)
    total_leagues = len(leagues_data)
    
    if title_text and any(c.isdigit() for c in title_text):
        clean_title = re.sub(r'Prediksi\s*Bola', '', title_text, flags=re.I).strip()
        date_label = f"📅 {clean_title}"
    else:
        today = get_wib_now()
        tomorrow = today + timedelta(days=1)
        bulan_map = {
            '01': 'Januari', '02': 'Februari', '03': 'Maret', '04': 'April',
            '05': 'Mei', '06': 'Juni', '07': 'Juli', '08': 'Agustus',
            '09': 'September', '10': 'Oktober', '11': 'November', '12': 'Desember'
        }
        b_now = bulan_map.get(today.strftime('%m'), today.strftime('%B'))
        b_tom = bulan_map.get(tomorrow.strftime('%m'), tomorrow.strftime('%B'))
        date_label = f"📅 {today.day} {b_now} - {tomorrow.day} {b_tom} {today.year}"
    
    options_html = '<option value="all">Semua Liga</option>\n'
    for liga in leagues_data.keys():
        options_html += f'<option value="{liga}">🏆 {liga}</option>\n'
        
    blocks_html = ""
    for liga, m_list in leagues_data.items():
        blocks_html += f'''
<div class="league-block" data-league="{liga}">
  <div class="league-inner">
    <div class="league-crown">
      <div class="crown-name">🏆 {liga} 🏆</div>
      <div class="match-count">{len(m_list)} Match</div>
    </div>
'''
        for idx, m in enumerate(m_list):
            parity = "even" if idx % 2 == 0 else "odd"
            teams_attr = f"{m['tim_home']} {m['tim_away']}".lower()
            skor_display = m['skor'].replace('-', ' : ')
            p = m['pred']
            
            logo_home = get_team_logo(m['tim_home'])
            logo_away = get_team_logo(m['tim_away'])
            fallback_home = generate_fallback_badge(m['tim_home'])
            fallback_away = generate_fallback_badge(m['tim_away'])
            
            blocks_html += f'''
    <div class="match-card {parity}" data-teams="{teams_attr}" onclick="toggleCard(this, event)">
      <div class="match-row">
        <div class="team-side left">
          <div class="team-line left-line">
            <img class="team-flag" src="{logo_home}" alt="{m['tim_home']}" onerror="this.onerror=null;this.src='{fallback_home}';" />
            <span class="team-name">{m['tim_home']}</span>
          </div>
        </div>
        <div class="score-center">
          <div class="score-num">{skor_display}</div>
          <div class="match-dt">{m['tanggal_raw']}<br />{m['jam']} WIB</div>
          <div class="market-line">{p['market_line']}</div>
        </div>
        <div class="team-side right">
          <div class="team-line right-line">
            <span class="team-name">{m['tim_away']}</span>
            <img class="team-flag" src="{logo_away}" alt="{m['tim_away']}" onerror="this.onerror=null;this.src='{fallback_away}';" />
          </div>
        </div>
        <div class="chev"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></div>
      </div>
      <div class="pred-panel" onclick="event.stopPropagation()">
        <div class="pred-inner">
          <div class="pred-grid">
            <div class="pred-col accent-green"><span class="col-title">Handicap</span><span class="col-answer green">{p['hdp']}</span><span class="col-note">{p['note_hdp']}</span></div>
            <div class="pred-col accent-green"><span class="col-title">Over / Under</span><span class="col-answer green">{p['ou']}</span><span class="col-note">{p['note_ou']}</span></div>
            <div class="pred-col accent-green"><span class="col-title">1X2</span><span class="col-answer green">{p['1x2']}</span><span class="col-note">{p['note_1x2']}</span></div>
            <div class="pred-col accent-gold"><span class="col-title">Skor Akurat</span><span class="col-answer">{skor_display}</span><span class="col-note">Top Pick</span></div>
          </div>
        </div>
      </div>
    </div>
'''
        blocks_html += '''  </div>
</div>
'''

    full_html = f'''<!-- KODE GENERATED BY LAPAK99 - Crown Top Edition -->
<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
<title>Prediksi Bola - LAPAK99</title>
<link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@700;900&family=Poppins:wght@400;600;700;900&display=swap" rel="stylesheet">

<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --g: #d45e04; --gl: #f27c22; --g2: #c04a00;
  --gd: #d45e0466; --gs: #d45e0422;
  --cr: #fff1c4;
  --bg: #000000; --bg2: #0d0d0d; --bg3: #111111;
}}
body {{ background: var(--bg); font-family: 'Poppins', sans-serif; color: var(--cr); min-height: 100vh; overflow-x: hidden; }}

.site-logo {{ 
    position: relative; 
    text-align: center; 
    padding: 22px 16px 10px; 
    height: 140px; 
    display: flex; 
    align-items: center; 
    justify-content: center; 
}}
.site-logo .logo-main {{ 
    width: 65%; 
    max-width: 240px; 
    filter: drop-shadow(0 0 22px var(--g)); 
    z-index: 2; 
    position: relative;
}}
.site-logo .mbappe-gif-left {{
    position: absolute;
    left: 20px;
    top: 50%;
    transform: translateY(-50%);
    height: 80px;
    width: auto;
    filter: drop-shadow(0 0 18px var(--gd));
    z-index: 1;
}}
.site-logo .mbappe-gif-right {{
    position: absolute;
    right: 20px;
    top: 50%;
    transform: translateY(-50%) scaleX(-1);
    height: 80px;
    width: auto;
    filter: drop-shadow(0 0 18px var(--gd));
    z-index: 1;
}}

.date-display {{ text-align: center; margin: 14px auto; width: 90%; padding: 13px 16px; border: 3px solid var(--g); border-radius: 15px; background: linear-gradient(180deg,#1a1a1a,#000); font-family: 'Cinzel',serif; font-size: clamp(13px,3.5vw,18px); font-weight: 700; color: var(--g); text-shadow: 0 0 14px var(--gd); letter-spacing: 2px; box-shadow: 0 0 20px var(--gd); word-break: break-word; }}
.stats-bar {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; width:90%; margin:0 auto 16px; }}
.stat-item {{ text-align:center; background:linear-gradient(180deg,#1a1a1a,#000); border:2px solid var(--g); border-radius:14px; padding:12px 8px; box-shadow:0 0 15px var(--gd); }}
.stat-num {{ display:block; font-family:'Cinzel',serif; font-size:clamp(20px,4vw,28px); font-weight:900; color:var(--g); text-shadow:0 0 10px var(--gd); }}
.stat-lbl {{ display:block; font-size:clamp(8px,1.6vw,11px); letter-spacing:2px; text-transform:uppercase; font-weight:900; color:var(--g); opacity:.86; margin-top:4px; }}
.marquee-wrap {{ overflow: hidden; white-space: nowrap; width: 90%; margin: 0 auto 16px; border: 3px solid var(--g); border-radius: 15px; background: linear-gradient(135deg,#1a1a1a,#000,#1a1a1a); padding: 15px 0; box-shadow: 0 0 20px var(--gd); }}
.marquee-inner {{ display: inline-block; animation: marquee 38s linear infinite; padding-left: 100%; font-size: clamp(11px,2.8vw,14px); font-weight: 900; color: var(--g); text-shadow: 0 0 10px var(--gd); letter-spacing: 1.5px; }}
@keyframes marquee {{ 0%{{transform:translateX(0)}} 100%{{transform:translateX(-100%)}} }}
.filter-wrap {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; width:90%; margin:0 auto 18px; }}
.filter-label {{ font-size:11px; color: var(--g); opacity: 0.75; text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700; margin-bottom: 7px; text-align: left; }}
.select-box {{ position:relative; }}
.select-box::after {{ content:"▼"; position:absolute; right:14px; top:50%; transform:translateY(-50%); color:var(--g); font-size:11px; pointer-events:none; }}
.fselect {{ width:100%; padding:10px 38px 10px 14px; background:rgba(0,0,0,0.85); border:2px solid var(--gd); border-radius:10px; color:var(--g); font-family:'Poppins',sans-serif; font-size:13px; font-weight:700; letter-spacing:0.8px; appearance:none; -webkit-appearance:none; outline:none; cursor:pointer; transition:border-color .2s, box-shadow .2s; text-align:center; text-align-last:center; }}
.fselect option {{ background:#0a0a0a; color:#fff; text-align:center; }}
.fselect:focus, .fselect:hover {{ border-color:var(--g); box-shadow:0 0 12px var(--gd); }}
.search-box {{ position:relative; }}
.search-icon {{ position:absolute; left:14px; top:50%; transform:translateY(-50%); font-size:16px; }}
.fsearch {{ width:100%; padding:10px 14px 10px 40px; background:rgba(0,0,0,0.85); border:2px solid var(--gd); border-radius:10px; color:var(--g); font-family:'Poppins',sans-serif; font-size:13px; font-weight:700; letter-spacing:0.8px; outline:none; transition:border-color .2s, box-shadow .2s; }}
.fsearch:focus, .fsearch:hover {{ border-color:var(--g); box-shadow:0 0 12px var(--gd); }}
.fsearch::placeholder {{ color:var(--gd); opacity:0.6; }}
.tap-hint {{ text-align:center; font-family:'Cinzel',serif; font-size:11px; letter-spacing:2px; text-transform:uppercase; font-weight:900; color:var(--g); border:1px dashed var(--gd); border-radius:10px; padding:12px; margin:8px auto 16px; width:90%; }}
.league-block {{ width: 90%; margin: 0 auto 22px; border: 3px solid var(--g); border-radius: 15px; padding: 5px; background: rgba(0,0,0,0.5); box-shadow: 0 0 20px var(--gd); }}
.league-inner {{ border-radius: 10px; overflow: hidden; border: 1px solid var(--gd); }}
.league-crown {{ position:relative; background: linear-gradient(180deg,#1a1200,#0d0d0d); padding: 8px 10px 6px; text-align: center; border-bottom: 1px solid var(--gs); }}
.crown-name {{ font-family: 'Cinzel',serif; font-size: clamp(9px,2.4vw,12px); font-weight: 900; color: var(--g); letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }}
.match-count {{ position:absolute; right:12px; top:8px; background:var(--g); color:#000; font-size:8px; font-weight:900; border-radius:999px; padding:4px 10px; text-transform:uppercase; }}
.match-card {{ margin:0; border:0; border-radius:0; background:linear-gradient(180deg,#2d2d2d,#1a1a1a); border-bottom:1px solid #2a2a2a; overflow:hidden; cursor:pointer; }}
.match-card:nth-child(even) {{ background:linear-gradient(180deg,#222,#2d2d2d); }}
.match-row {{ display:grid; grid-template-columns:1fr 100px 1fr 22px; gap:6px; align-items:center; min-height:68px; padding:8px 14px; }}
.team-side {{ min-width:0; }}
.team-line {{ display:flex; align-items:center; gap:8px; min-width:0; }}
.left-line {{ justify-content:flex-start; }}
.right-line {{ justify-content:flex-end; }}
.team-flag {{ width:32px; height:32px; object-fit:contain; flex-shrink:0; filter:drop-shadow(0 0 6px rgba(0,0,0,.7)); }}
.team-name {{ display:block; font-weight:900; font-size:clamp(10px,2vw,13px); line-height:1.2; color:#d8f8ff; text-shadow:0 0 6px var(--gd); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.score-center {{ text-align:center; line-height:1.05; }}
.score-num {{ font-family:'Cinzel',serif; font-size:clamp(18px,4vw,24px); font-weight:900; color:var(--g); letter-spacing:2px; text-shadow:0 0 10px var(--gd); }}
.match-dt {{ font-size:clamp(8px,1.6vw,10px); font-weight:700; color:var(--g); opacity:.8; line-height:1.5; margin-top:4px; }}
.market-line {{ display:none; }}
.chev {{ color:var(--g); opacity:.9; transition:transform 0.3s ease; }}
.match-card.open .chev {{ transform:rotate(180deg); }}
.pred-panel {{ max-height:0; overflow:hidden; transition:max-height .35s ease; background:#191919; }}
.match-card.open .pred-panel {{ max-height:500px; }}
.pred-inner {{ padding:12px 14px 16px; }}
.pred-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }}
.pred-col {{ position:relative; text-align:center; background:var(--bg2); border:1px solid var(--gs); border-radius:10px; padding:12px 6px; overflow:hidden; }}
.pred-col::before {{ content:''; position:absolute; top:0; left:0; right:0; height:3px; }}
.accent-green::before {{ background:linear-gradient(90deg,transparent,#00d166,transparent); }}
.accent-gold::before {{ background:linear-gradient(90deg,transparent,var(--g),transparent); }}
.col-title {{ font-size:8px; font-weight:900; color:var(--g); text-transform:uppercase; display:block; margin-bottom:5px; opacity:.9; }}
.col-answer {{ font-size:11px; font-weight:900; color:var(--g); display:block; }}
.col-answer.green {{ color:#00d166; }}
.col-note {{ font-size:8px; color:#aaa; display:block; margin-top:3px; }}

@media (max-width:640px) {{
  .site-logo {{ height:100px; padding:12px 8px; }}
  .site-logo .logo-main {{ max-width:160px; }}
  .site-logo .mbappe-gif-left {{ left:8px; height:50px; }}
  .site-logo .mbappe-gif-right {{ right:8px; height:50px; }}
  .filter-wrap {{ grid-template-columns:1fr; }}
  .match-row {{ grid-template-columns:1fr 80px 1fr 16px; padding:6px 8px; gap:4px; min-height:56px; }}
  .pred-grid {{ grid-template-columns:repeat(2,1fr); }}
  .team-name {{ font-size:9px; }}
  .team-flag {{ width:24px; height:24px; }}
  .score-num {{ font-size:16px; }}
}}
</style>
</head>
<body>

<header class="site-logo">
  <img class="mbappe-gif-left" src="https://photoku.io/images/2026/05/31/giffmbappee-finall.gif" alt="Mbappe" />
  <img class="logo-main" src="https://cdn.areabermain.club/assets/cdn/az1/2025/10/14/20251014/43512f57bb3f3e54960ee9a4dbe06e5a/lapak99-logo4.png" alt="LAPAK99" />
  <img class="mbappe-gif-right" src="https://photoku.io/images/2026/05/31/giffmbappee-finall.gif" alt="Mbappe" />
</header>

<div class="date-display"><span class="date-text">{date_label}</span></div>

<div class="stats-bar">
  <div class="stat-item"><span class="stat-num">{total_matches}</span><span class="stat-lbl">Pertandingan</span></div>
  <div class="stat-item"><span class="stat-num">{total_leagues}</span><span class="stat-lbl">Liga</span></div>
  <div class="stat-item"><span class="stat-num">100%</span><span class="stat-lbl">Terupdate</span></div>
</div>

<div class="marquee-wrap">
  <div class="marquee-inner">⚽️ PREDIKSI BOLA TERUPDATE ! Tunggu apa lagi? Daftar di LAPAK99 dan nikmati pengalaman taruhan yang seru dengan peluang besar! ⚽️ &nbsp;&nbsp;&nbsp;&nbsp; ⚽️ PREDIKSI BOLA TERUPDATE ! Tunggu apa lagi? Daftar di LAPAK99 dan nikmati pengalaman taruhan yang seru dengan peluang besar! ⚽️</div>
</div>

<div class="filter-wrap">
  <div>
    <span class="filter-label">🏆 Pilih Liga</span>
    <div class="select-box">
      <select class="fselect" id="leagueFilter" onchange="filterLeague(this.value)">
        {options_html}
      </select>
    </div>
  </div>
  <div>
    <span class="filter-label">🔍 Cari Tim</span>
    <div class="search-box">
      <span class="search-icon">⚽</span>
      <input class="fsearch" id="teamSearch" type="text" placeholder="Nama tim..." oninput="searchTeam(this.value)" />
    </div>
  </div>
</div>

<div class="tap-hint">
  <span class="hint-arrow">⬇</span> <span class="hint-text">Klik pertandingan di bawah untuk melihat prediksi</span> <span class="hint-arrow">⬇</span>
</div>

<div id="matchesContainer">
{blocks_html}
</div>

<script>
function toggleCard(card, event) {{
  card.classList.toggle('open');
}}

function filterLeague(val) {{
  const blocks = document.querySelectorAll('.league-block');
  blocks.forEach(b => {{
    if (val === 'all' || b.getAttribute('data-league') === val) {{
      b.style.display = '';
    }} else {{
      b.style.display = 'none';
    }}
  }});
}}

function searchTeam(query) {{
  const q = query.toLowerCase().trim();
  const blocks = document.querySelectorAll('.league-block');
  
  blocks.forEach(b => {{
    const cards = b.querySelectorAll('.match-card');
    let hasVisible = false;
    cards.forEach(c => {{
      const teams = c.getAttribute('data-teams') || '';
      if (!q || teams.includes(q)) {{
        c.style.display = '';
        hasVisible = true;
      }} else {{
        c.style.display = 'none';
      }}
    }});
    b.style.display = hasVisible ? '' : 'none';
  }});
}}
</script>

</body>
</html>
'''
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(full_html)
    with open("prediksi_lapak99.html", 'w', encoding='utf-8') as f:
        f.write(full_html)
    print(f"Data HTML berhasil disimpan ke: {OUTPUT_HTML} & prediksi_lapak99.html")

def simpan_csv(matches):
    if not matches:
        return
    
    tanggal_file = get_wib_now().strftime("%d_%B_%Y")
    csv_file = os.path.join(OUTPUT_FOLDER, f"prediksi_{tanggal_file}.csv")
    
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['liga', 'tanggal', 'jam', 'tim_home', 'tim_away', 'skor']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in matches:
            writer.writerow({
                'liga': m.get('liga', ''),
                'tanggal': m.get('tanggal', ''),
                'jam': m.get('jam', ''),
                'tim_home': m.get('tim_home', ''),
                'tim_away': m.get('tim_away', ''),
                'skor': m.get('skor', '')
            })
    
GITHUB_TOKEN = os.environ.get("GH_TOKEN", os.environ.get("GITHUB_TOKEN", ""))
if not GITHUB_TOKEN and os.path.exists("github_token.txt"):
    try:
        with open("github_token.txt", "r", encoding="utf-8") as f:
            GITHUB_TOKEN = f.read().strip()
    except Exception:
        pass
GITHUB_REPO = "lapak99laris-code/prediksi-bola"

def upload_ke_github():
    if "GITHUB_ACTIONS" in os.environ:
        print("Berjalan di GitHub Actions (update ditangani otomatis oleh Git workflow).")
        return
        
    try:
        if not os.path.exists(OUTPUT_HTML):
            return
            
        with open(OUTPUT_HTML, 'r', encoding='utf-8') as f:
            content = f.read()
            
        content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        url = f'https://api.github.com/repos/{GITHUB_REPO}/contents/index.html'
        r_get = requests.get(url, headers=headers, timeout=10)
        sha = r_get.json().get('sha') if r_get.status_code == 200 else None
        
        data = {
            'message': f"Auto-update prediksi bola {get_wib_now().strftime('%d-%m-%Y %H:%M')}",
            'content': content_b64
        }
        if sha:
            data['sha'] = sha
            
        r_put = requests.put(url, headers=headers, json=data, timeout=15)
        if r_put.status_code in [200, 201]:
            print("Berhasil upload ke GitHub Pages!")
            print("URL Online: https://lapak99laris-code.github.io/prediksi-bola/")
        else:
            print(f"Gagal upload ke GitHub (HTTP {r_put.status_code})")
    except Exception as e:
        print(f"Error upload ke GitHub: {e}")

def main():
    print("="*70)
    print("AUTO PREDIKSI BOLA")
    print(f"Tanggal sistem: {get_wib_now().strftime('%d %B %Y')}")
    print("="*70)
    
    load_team_logos()
    
    try:
        link, title_text, is_today = cari_link_prediksi()
        if not link:
            print("Link tidak ditemukan!")
            return
        
        print(f"Link ditemukan: {link}")
        if is_today:
            print(f"[STATUS] Sukses! Menemukan rilis prediksi hari ini: {title_text}")
        else:
            print(f"[STATUS] Website sumber belum mempublikasikan tanggal hari ini.")
            print(f"[STATUS] Menggunakan data artikel paling baru di sumber: {title_text}")
            
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        resp = requests.get(link, headers=headers, timeout=15)
        resp.raise_for_status()
        print("Halaman detail berhasil diambil!\n")
        
        matches = ekstrak_pertandingan_html(resp.text)
        
        if matches:
            simpan_csv(matches)
            simpan_html(matches, title_text)
            print("\nMengupload ke GitHub Pages...")
            upload_ke_github()
            print("\n" + "="*70)
            print("SELESAI! CSV, HTML & GITHUB PAGES BERHASIL DIUPDATE!")
            print("="*70)
        else:
            print("Tidak ada pertandingan ditemukan!")
            
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
