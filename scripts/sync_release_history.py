"""
SolarWatch App Release History Synchronizer (Mirror Site Edition)
===============================================================
ETL script to fetch historical application releases from third-party 
mirrors (like AppBrain) to bypass official store limitations and 
retrieve the full 180-day 'Zero Moment' (T) timeline.
"""

import sys
import os
import time
import random
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
import dateutil.parser
from bs4 import BeautifulSoup
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Support relative imports for standalone execution
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.settings import TargetApp
from src.config.constants import SourcePlatform
from src.models.database import Base, AppRelease

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "solarwatch.db")
SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.yaml")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0"
]

def load_targets():
    with open(SETTINGS_PATH, "r") as f:
        config = yaml.safe_load(f)
    return [TargetApp(**t) for t in config['targets']]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

def fetch_ios_history(app_id: str, app_name: str) -> list[dict]:
    """
    Attempt to fetch iOS history. 
    Apple is notoriously difficult to scrape deeply without internal tokens.
    We try the generic web method first, then fallback to lookup.
    """
    versions = []
    headers = get_headers()
    
    # Try multiple regions
    for region in ['gb', 'de', 'us', 'au']:
        url = f"https://apps.apple.com/{region}/app/id{app_id}"
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            history_items = soup.select('.version-history__item')
            
            for item in history_items:
                v_node = item.select_one('.version-history__item__version-number')
                d_node = item.select_one('.version-history__item__release-date')
                c_node = item.select_one('.we-truncate')
                
                if v_node and d_node:
                    dt = dateutil.parser.isoparse(d_node.get('datetime'))
                    versions.append({
                        "version": v_node.text.strip(),
                        "release_date": dt,
                        "changelog": c_node.text.strip() if c_node else ""
                    })
            if versions:
                break
        except Exception:
            continue
            
    # Fallback to iTunes API
    if not versions:
        try:
            lookup = requests.get(f"https://itunes.apple.com/lookup?id={app_id}&country=de").json()
            if lookup.get('resultCount', 0) > 0:
                res = lookup['results'][0]
                v = res.get('version')
                rd = res.get('currentVersionReleaseDate')
                if v and rd:
                    versions.append({
                        "version": v,
                        "release_date": dateutil.parser.isoparse(rd),
                        "changelog": res.get('releaseNotes', '')
                    })
        except Exception:
            pass
            
    if not versions:
        print(f"  [!] iOS Mirror Scrape failed for {app_name} ({app_id})")
    else:
        print(f"  [✓] Found {len(versions)} iOS version(s) for {app_name}")
        
    return versions

def fetch_android_appbrain(pkg_name: str, app_name: str) -> list[dict]:
    """
    Scrapes AppBrain for historical Android versions.
    URL Format: https://www.appbrain.com/app/{slug}/{pkg_name}/changelog
    """
    versions = []
    # Using generic slug "app" as AppBrain often redirects correctly, 
    # but we will just target the main app page and look for the changelog table.
    url = f"https://www.appbrain.com/app/{pkg_name}"
    
    try:
        resp = requests.get(url, headers=get_headers(), timeout=15)
        # If successfully loaded, parse the page. AppBrain might list recent changes.
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # AppBrain usually has a changes table or list.
            # We'll look for anything matching "Version history" or "Changelog"
            changelog_section = soup.find('div', id='changelog')
            
            if changelog_section:
                # This is highly dependent on AppBrain's current DOM.
                # A common pattern is rows with version numbers and dates.
                rows = changelog_section.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        v_text = cols[0].text.strip()
                        d_text = cols[1].text.strip()
                        
                        # Very basic date parsing from typical AppBrain format
                        try:
                            # Sometimes it might just be the main page's info box
                            dt = dateutil.parser.parse(d_text, fuzzy=True)
                            versions.append({
                                "version": v_text,
                                "release_date": dt.replace(tzinfo=timezone.utc), # Ensure UTC
                                "changelog": ""
                            })
                        except Exception:
                            continue
            
            # If no changelog section found, just try to grab the latest version from the info table.
            if not versions:
                info_table = soup.find('table', class_='infotable')
                if info_table:
                    v_str = ""
                    d_dt = None
                    for tr in info_table.find_all('tr'):
                        th = tr.find('th')
                        if th:
                            if "Latest version" in th.text:
                                v_str = tr.find('td').text.strip()
                            if "Updated" in th.text:
                                d_text = tr.find('td').text.strip()
                                try:
                                    d_dt = dateutil.parser.parse(d_text, fuzzy=True).replace(tzinfo=timezone.utc)
                                except Exception:
                                    pass
                    if v_str and d_dt:
                        versions.append({
                            "version": v_str,
                            "release_date": d_dt,
                            "changelog": ""
                        })

    except Exception as e:
        print(f"  [!] AppBrain network error: {e}")
        
    # If AppBrain completely fails, we use a fallback heuristic:
    # If we truly want to demonstrate the system, we can infer versions from ApkPure or similar,
    # but for script robustness, if we get nothing, we print a warning.
    if not versions:
        print(f"  [!] Android Mirror Scrape failed for {app_name} ({pkg_name}). Anti-bot protections likely active.")
    else:
        print(f"  [✓] Found {len(versions)} Android version(s) for {app_name}")
        
    return versions

def main():
    print("🚀 Initializing SolarWatch Release History Synchronizer (Mirror Mode)...")
    targets = load_targets()
    
    engine = create_engine(f"sqlite:///{DB_PATH}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    total_new = 0
    now_utc = datetime.now(timezone.utc)
    cutoff_date = now_utc - timedelta(days=180)
    
    for target in targets:
        print(f"\n🔍 Targeting: {target.name}")
        
        # 1. Sync iOS
        print(f"  - Querying iOS Mirrors...")
        ios_releases = fetch_ios_history(target.app_store_id, target.name)
        for rel in ios_releases:
            if rel['release_date'] < cutoff_date:
                continue
                
            is_major = rel['version'].endswith('.0') or rel['version'].endswith('.0.0')
            
            exists = session.query(AppRelease).filter_by(
                app_name=target.name,
                platform=SourcePlatform.APP_STORE,
                version=rel['version']
            ).first()
            
            if not exists:
                rec = AppRelease(
                    app_name=target.name,
                    platform=SourcePlatform.APP_STORE,
                    version=rel['version'],
                    release_date=rel['release_date'].replace(tzinfo=None),
                    changelog=rel['changelog'],
                    is_major_update=is_major
                )
                session.add(rec)
                total_new += 1
                
        time.sleep(random.uniform(1.5, 3.5))
        
        # 2. Sync Android (AppBrain Mirror)
        print(f"  - Querying Android Mirrors (AppBrain)...")
        android_releases = fetch_android_appbrain(target.google_play_id, target.name)
        for rel in android_releases:
            if rel['release_date'] < cutoff_date:
                continue
                
            is_major = rel['version'].endswith('.0') or rel['version'].endswith('.0.0')
            
            exists = session.query(AppRelease).filter_by(
                app_name=target.name,
                platform=SourcePlatform.GOOGLE_PLAY,
                version=rel['version']
            ).first()
            
            if not exists:
                rec = AppRelease(
                    app_name=target.name,
                    platform=SourcePlatform.GOOGLE_PLAY,
                    version=rel['version'],
                    release_date=rel['release_date'].replace(tzinfo=None),
                    changelog=rel['changelog'],
                    is_major_update=is_major
                )
                session.add(rec)
                total_new += 1
                
        time.sleep(random.uniform(2.0, 4.0))
        
    try:
        session.commit()
        print(f"\n✅ Deep Mirror Sync Complete! Recovered {total_new} historical release records into solarwatch.db")
    except Exception as e:
        session.rollback()
        print(f"\n❌ Database error during commit: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    main()
