#!/usr/bin/env python3
"""Clean non-Latin characters (CJK, Arabic, Thai, Cyrillic, etc.) from all stories in the DB."""

import sqlite3
import re
import os

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.config import config
DB_PATH = config.DB_PATH

# Known CJK → Indonesian replacements (common hallucinations)
REPLACEMENTS = {
    '乐器': 'instrumen musik',
    '帖子': 'postingan',
    '悲剧': 'tragedi',
    '宣言': 'deklarasi',
    '愤怒': 'kemarahan',
    '末': '',
    '其他地方': 'wilayah lain',
    '救援': 'penyelamatan',
    '地方': 'wilayah',
    '浪漫主义': 'romantisme',
    '简化': 'penyederhanaan',
    '预言': 'ramalan',
    '模糊': 'samar',
    '精英': 'elit',
    '动物': 'hewan',
}

# Catch ALL non-Latin scripts: CJK, Arabic, Thai, Cyrillic, Devanagari, etc.
# Keeps: ASCII + Latin Extended + common symbols/punctuation
NON_LATIN_RE = re.compile(r'[^\x00-\x7F\u00C0-\u024F\u2000-\u206F\u20A0-\u20CF\u2100-\u214F\u2190-\u21FF\u2200-\u22FF\u2500-\u257F\u2580-\u259F\u25A0-\u25FF\u2600-\u26FF\u2700-\u27BF\uFE10-\uFE1F\uFE30-\uFE4F\uFE50-\uFE6F\uFF00-\uFFEF\u2010-\u2027\u2030-\u205E\u00A0-\u00FF]+')

def clean_text(text):
    # First replace known multi-char CJK words with Indonesian
    for cn, id_word in REPLACEMENTS.items():
        text = text.replace(cn, id_word)
    # Then strip any remaining CJK characters
    text = NON_LATIN_RE.sub('', text)
    # Clean up spaces
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def main():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('SELECT id, topic, story_body, story_title FROM articles WHERE story_body IS NOT NULL').fetchall()
    
    fixed = 0
    for r in rows:
        original_body = r[2]
        cleaned_body = clean_text(original_body)
        original_title = r[3] or ''
        cleaned_title = clean_text(original_title) if original_title else ''
        changed = False
        if cleaned_body != original_body:
            conn.execute('UPDATE articles SET story_body = ? WHERE id = ?', (cleaned_body, r[0]))
            changed = True
        if original_title and cleaned_title != original_title:
            conn.execute('UPDATE articles SET story_title = ? WHERE id = ?', (cleaned_title, r[0]))
            changed = True
        if changed:
            fixed += 1
            # Count remaining CJK
            remaining = NON_LATIN_RE.findall(cleaned_body)
            print(f'  id={r[0]:>3} ({r[1]:<30}): {len(original_body):>6} -> {len(cleaned_body):>6} chars, {len(remaining)} remaining')
    
    conn.commit()
    conn.close()
    print(f'\nDone! {fixed} stories cleaned.')
    
    # Verify
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute('SELECT id, story_body FROM articles WHERE story_body IS NOT NULL').fetchall()
    all_clean = True
    for r in rows:
        remaining = NON_LATIN_RE.findall(r[1])
        if remaining:
            all_clean = False
            print(f'  ⚠️ id={r[0]}: still has {len(remaining)} CJK chars')
    if all_clean:
        print('✅ All stories are now clean!')
    conn.close()

if __name__ == '__main__':
    main()
