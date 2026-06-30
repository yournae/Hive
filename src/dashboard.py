from flask import Flask, render_template_string
from . import database as db
from .config import config
app = Flask(__name__)
TPL = """<!doctype html><html><head><meta charset="utf-8"><title>Hive</title>
<meta http-equiv="refresh" content="30"><style>
body{font-family:system-ui,Arial;margin:2rem;background:#0f172a;color:#e2e8f0}
.card{display:inline-block;background:#1e293b;padding:1rem 1.5rem;border-radius:12px;margin:.5rem}
.card b{font-size:2rem;display:block}table{width:100%;border-collapse:collapse;margin-top:1rem}
td,th{padding:.5rem;border-bottom:1px solid #334155;text-align:left;font-size:.9rem}
a{color:#38bdf8}.ok{color:#4ade80}.fail{color:#f87171}</style></head><body>
<h1>🐝 Hive</h1>
<div class="card">Total Artikel<b>{{s.total_articles}}</b></div>
<div class="card">Siap Posting<b>{{s.ready}}</b></div>
<div class="card">Sudah Diposting<b>{{s.posted}}</b></div>
<div class="card">Gagal<b>{{s.failed}}</b></div>
<p>Jadwal posting: <b>{{times}}</b> ({{tz}}) &middot; <span class="ok">● ONLINE</span></p>
<h2>Posting Terbaru</h2>
<table><tr><th>Waktu (UTC)</th><th>Judul</th><th>Status</th><th>Link / Error</th></tr>
{% for p in posts %}<tr><td>{{p.posted_at}}</td><td>{{p.title}}</td>
<td class="{{'ok' if p.status=='success' else 'fail'}}">{{p.status}}</td>
<td>{% if p.post_url %}<a href="{{p.post_url}}" target="_blank">buka</a>{% else %}{{p.error_message}}{% endif %}</td>
</tr>{% endfor %}</table></body></html>"""

@app.route("/")
def index():
    db.init_db()
    return render_template_string(TPL, s=db.get_stats(), posts=db.get_recent_posts(),
                                  times=", ".join(config.POST_TIMES), tz=config.TIMEZONE)

def serve(host="0.0.0.0", port=8080):
    app.run(host=host, port=port)
