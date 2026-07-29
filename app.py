from flask import Flask, render_template_string, request, redirect, session, url_for, jsonify, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room
import json, os, base64, time, random, string, threading
from datetime import datetime
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = "genie_v33_whatsapp"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

CENTRAL_SERVER = "https://genie-facteur.onrender.com"
DB_FILE = "genie_db.json"
db_lock = threading.Lock()

def load_db():
    with db_lock:
        if os.path.exists(DB_FILE):
            with open(DB_FILE) as f: return json.load(f)
        return {"USERS": {}, "MESSAGES": {}, "UNREAD": {}, "ARCHIVED": {}, "CHANNELS": {}} # AJOUT CHANNELS

def save_db(db):
    def _save():
        with db_lock:
            tmp = DB_FILE + ".tmp"
            with open(tmp, "w") as f: json.dump(db, f, separators=(',', ':'))
            os.replace(tmp, DB_FILE)
    threading.Thread(target=_save, daemon=True).start()

def gen_code_port():
    db = load_db()
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in db["USERS"]:
            return code

CSS = """* {box-sizing: border-box; margin:0; padding:0; font-family: 'Segoe UI', Roboto, sans-serif; -webkit-user-select:none; user-select:none;} /* AJOUT: bloque selection */
body {background:#111B21; color:#E9EDEF;}
.header {background:#202C33; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10;}
.header-actions{display:flex; gap:15px;}
.header-actions button{background:none; border:none; color:white; font-size:16px; cursor:pointer; font-weight:600;}
.btn {background:#00A884; color:white; border:none; padding:14px 15px; border-radius:10px; cursor:pointer; font-weight:600; width:100%; margin-top:12px; font-size:16px; text-decoration:none; display:block; text-align:center;}
.btn-danger {background:#D93025;}
.btn-gray {background:#2A3942;}
.input {padding:14px; border:none; border-radius:10px; background:#2A3942; color:white; width:100%; margin-top:6px; font-size:16px;}
.form-group {margin-bottom:15px;}
.avatar {width:40px; height:40px; border-radius:50%; background:#00A884; display:flex; align-items:center; justify-content:center; font-weight:bold; background-size:cover; background-position:center; color:white; position:relative; cursor:pointer;}
.avatar-big {width:150px; height:150px; border-radius:50%; margin:0 auto 20px; display:flex; align-items:center; justify-content:center; background:#2A3942; font-size:60px; font-weight:bold; border:4px solid #00A884; background-size:cover; background-position:center;}
.box {background:#202C33; padding:25px; border-radius:20px; max-width:450px; margin:30px auto; width:90%; box-shadow:0 4px 20px rgba(0,0,0,0.3);}
.code-info {padding:14px; background:#000; font-size:20px; color:#00A884; border-radius:10px; text-align:center; letter-spacing:4px; font-weight:bold; margin:10px 0; user-select:all;}
.contact-list {flex:1; overflow-y:auto;}
.contact{padding:14px 16px; display:flex; align-items:center; gap:14px; cursor:pointer; border-bottom:1px solid #2A3942; position:relative; user-select:none;}
.contact.selected{background:#2A3942;}
.contact:hover{background:#2A3942;}
.contact-info{flex:1;}
.add-bar{padding:10px; background:#202C33; display:flex; gap:10px; position:sticky; bottom:0;}
.messages{padding:15px; flex:1; overflow-y:auto; background:#0B141A; display:flex; flex-direction:column;}
.msg{padding:9px 13px; border-radius:8px; margin:5px 0; max-width:78%; font-size:15px;}
.msg.me{background:#005C4B; align-self:flex-end; border-bottom-right-radius:2px;}
.msg.you{background:#202C33; align-self:flex-start; border-bottom-left-radius:2px;}
.time{font-size:11px; color:#8696A0; text-align:right; margin-top:4px;}
.send-box{display:flex; padding:10px; background:#202C33; gap:10px; align-items:center;}
.check.gray{color:#8696A0;}.check.blue{color:#53BDEB;}
.alert{background:#00A884; padding:12px; border-radius:10px; margin-bottom:15px; text-align:center; font-weight:600;}
.crop-modal {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:#000; z-index:99; flex-direction:column; justify-content:center; align-items:center;}
.crop-area {position:relative; width:100%; height:100%; display:flex; justify-content:center; align-items:center; overflow:hidden; touch-action:none;}
.crop-circle {position:absolute; width:200px; height:200px; border:4px solid #00A884; border-radius:50%; box-shadow:0 0 0 9999px rgba(0,0,0,0.8); pointer-events:none;}
.crop-img {position:absolute; cursor:grab; max-width:none; left:50%; top:50%; touch-action:none; user-select:none;}
.crop-buttons {position:absolute; bottom:0; width:100%; padding:15px; background:#202C33; display:flex; gap:10px;}
h2{text-align:center; margin-bottom:15px; color:#00A884;}
label {display:block; margin-top:5px; font-size:14px; color:#8696A0;}
.mic-btn{background:#00A884; border:none; border-radius:50%; width:48px; height:48px; font-size:22px; color:white; cursor:pointer; touch-action:none;} /* AJOUT: bloque menu copie */
.mic-btn.recording{background:red; animation: pulse 1s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,0,0,0.7)} 70%{box-shadow:0 0 0 10px rgba(255,0,0,0)} 100%{box-shadow:0 0 0 0 rgba(255,0,0,0)}}
.audio-player{width:200px; height:40px;}
.badge{background:#00A884; color:white; border-radius:50%; min-width:22px; height:22px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:bold; padding:2px 6px;}
.popup {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:100; justify-content:center; align-items:center;}
.popup-box {background:#202C33; padding:25px; border-radius:15px; width:90%; max-width:350px; text-align:center;}
.popup-buttons {display:flex; gap:10px; margin-top:20px;}
/* AJOUT: BARRE BAS + PAGES */
.bottom-nav{display:flex; background:#202C33; justify-content:space-around; padding:8px 0; position:sticky; bottom:0; z-index:20;}
.nav-item{flex:1; text-align:center; color:#8696A0; font-size:12px; cursor:pointer; padding:5px;}
.nav-item.active{color:#00A884;}
.nav-item span{font-size:22px; display:block;}
.page{display:none; flex:1; flex-direction:column; height:calc(100vh - 120px);}
.page.active{display:flex;}
.editor-video{padding:20px; text-align:center; color:#8696A0;}
.channel-card{background:#2A3942; padding:15px; margin:10px; border-radius:10px; display:flex; gap:10px; align-items:center;}
"""

#... TOUT TES HTML LOGIN, REGISTER, SETTINGS, ARCHIVES RESTENT IDENTIQUE...

CONTACTS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Chats</title><style>{{ CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head>
<body style="display:flex; flex-direction:column; height:100vh;">
<div class="header" id="mainHeader">
<h2>GenieChat</h2>
<div class="header-actions">
<a href="/archives" style="color:white; text-decoration:none;">📦</a>
<a href="/settings"><div class="avatar" style="background-image:url('{{ photo }}')">{{ '' if photo else nom[0]|upper }}</div></a>
</div>
</div>

<div class="header" id="selectionHeader" style="display:none; background:#D93025;">
<button onclick="exitSelection()">✕</button>
<h2 id="selectedCount">0 sélectionné</h2>
<div class="header-actions">
<button onclick="archiveSelected()">Archiver</button>
<button onclick="confirmDelete()">Supprimer</button>
</div>
</div>

<div id="page-contacts" class="page active">
<div class="contact-list" id="contact-list">{% for c in contacts %}
<div class="contact" data-code="{{ c }}" onmousedown="startLongPress('{{ c }}')" onmouseup="endLongPress()" onmouseleave="endLongPress()" ontouchstart="startLongPress('{{ c }}')" ontouchend="endLongPress()">
<div class="avatar" style="background-image:url('{{ users[c].photo }}')">{{ '' if users[c].photo else users[c].nom[0]|upper }}</div>
<div class="contact-info"><b>{{ users[c].nom }}</b><br><small style="color:#8696A0;">{{ c }}</small></div>
{% if unread.get(c, 0) > 0 %}<div class="badge">{{ unread[c] }}</div>{% endif %}
</div>{% endfor %}</div>
<div class="add-bar"><form method="POST" action="/ajouter" style="display:flex; width:100%; gap:10px;">
<input name="code_ami" placeholder="Entrer CODE de l'ami" class="input" required><button class="btn" style="width:80px;">Créer</button></form></div>
</div>

<div id="page-statut" class="page"><div class="editor-video"><h3>Éditeur Statut</h3><p>Ajoute photo/video 24h. Bientôt.</p><input type="file" accept="image/*,video/*" class="btn btn-gray"></div></div>

<div id="page-chaines" class="page">
<div style="padding:10px;"><input id="searchChannel" class="input" placeholder="Rechercher une chaîne"><button class="btn" onclick="createChannel()">+ Créer ma chaîne</button></div>
<div id="channelsList" class="contact-list"></div></div>

<div id="page-actu" class="page"><div class="editor-video"><h3>Actualités IA</h3><p>Résumé de tes messages non lus. Désactivé pour le moment.</p></div></div>

<div class="bottom-nav">
<div class="nav-item active" onclick="showPage('contacts')"><span>💬</span>Accueil</div>
<div class="nav-item" onclick="showPage('statut')"><span>⭕</span>Statut</div>
<div class="nav-item" onclick="showPage('chaines')"><span>📢</span>Chaînes</div>
<div class="nav-item" onclick="showPage('actu')"><span>📰</span>Actualités</div>
</div>

<div class="popup" id="deletePopup"><div class="popup-box"><h3>Supprimer le contact?</h3><p id="deleteText"></p><div class="popup-buttons"><button class="btn btn-gray" onclick="closePopup()">Annuler</button><button class="btn btn-danger" onclick="deleteConfirmed()">Supprimer</button></div></div></div>

<script>
const socket=io("{{ central }}"); const MY_CODE="{{ my_code }}";
let selectedContacts = []; let longPressTimer; let isSelecting = false;

socket.emit('join',{code:MY_CODE});

function showPage(page){
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(p=>p.classList.remove('active'));
    document.getElementById('page-'+page).classList.add('active');
    event.currentTarget.classList.add('active');
    if(page=='chaines'){ loadChannels(); }
}

function startLongPress(code){ longPressTimer = setTimeout(()=>{ enterSelectionMode(code); }, 600); }
function endLongPress(){ clearTimeout(longPressTimer); }
function enterSelectionMode(code){ isSelecting = true; selectContact(code); }

function selectContact(code){
    const el = document.querySelector(`[data-code="${code}"]`);
    if(!el) return;
    if(selectedContacts.includes(code)){
        selectedContacts = selectedContacts.filter(c=>c!=code);
        el.classList.remove('selected');
    } else {
        selectedContacts.push(code);
        el.classList.add('selected');
    }
    updateSelectionHeader();
}

function updateSelectionHeader(){
    if(selectedContacts.length > 0){
        document.getElementById('mainHeader').style.display='none';
        document.getElementById('selectionHeader').style.display='flex';
        document.getElementById('selectedCount').innerText = selectedContacts.length + ' sélectionné';
    }
}

function exitSelection(){
    isSelecting = false; selectedContacts = [];
    document.querySelectorAll('.contact.selected').forEach(el=>el.classList.remove('selected'));
    document.getElementById('mainHeader').style.display='flex';
    document.getElementById('selectionHeader').style.display='none';
}

function confirmDelete(){ document.getElementById('deleteText').innerText = `Supprimer ${selectedContacts.length} contact(s) et tous leurs messages?`; document.getElementById('deletePopup').style.display='flex'; }
function closePopup(){ document.getElementById('deletePopup').style.display='none'; }
function deleteConfirmed(){ fetch('/delete_contacts', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({contacts: selectedContacts})}).then(()=>{ location.reload(); }); }
function archiveSelected(){ fetch('/archive_contacts', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({contacts: selectedContacts})}).then(()=>{ location.reload(); }); }

function loadChannels(){ fetch('/get_channels').then(r=>r.json()).then(data=>{ let html=''; data.forEach(ch=>{ html+=`<div class="channel-card" onclick="openChannel('${ch.id}')"><div class="avatar">${ch.name[0]}</div><div><b>${ch.name}</b><br><small>${ch.desc}</small></div></div>` }); document.getElementById('channelsList').innerHTML=html || '<p style="text-align:center; padding:20px;">Aucune chaîne</p>'; }) }
function createChannel(){ let name=prompt("Nom de ta chaîne:"); if(name){ fetch('/create_channel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(()=>loadChannels()) } }
function openChannel(id){ alert("Ouverture chaîne: " + id + ". Mode lecture seule.") }

document.querySelectorAll('.contact').forEach(el=>{
    el.addEventListener('click', ()=>{ if(!isSelecting){ location.href='/chat/'+el.dataset.code; } else { selectContact(el.dataset.code); } });
});

// SYNC MESSAGES
function sendToApp(data){ if(window.Android){ Android.saveMessage(JSON.stringify(data)); } }
function syncMessages(){ {% for c in contacts %} fetch('/get_msg/{{ c }}').then(r=>r.json()).then(msgs=>{ localStorage.setItem('chat_{{ my_code }}_{{ c }}', JSON.stringify(msgs)); msgs.forEach(m => sendToApp({contact:'{{ c }}', message:m.msg, heure:m.time, envoyeur:m.from})); }); {% endfor %} }
syncMessages(); socket.on('new_message_alert', ()=>{ syncMessages(); });
</script>
</body></html>"""

#... CHAT_HTML RESTE IDENTIQUE A TOI...

def get_user():
    code = session.get('code')
    db = load_db()
    return code, db["USERS"].get(code), db

#... TOUTES TES ROUTES /login /register /settings /logout /contacts /archives /delete_contacts /archive_contacts /ajouter /chat /get_msg RESTENT IDENTIQUE...

# AJOUT: ROUTES POUR CHAINES
@app.route('/create_channel', methods=['POST'])
def create_channel():
    code, user, db = get_user()
    if not code: return jsonify({"status":"error"}), 403
    data = request.json
    ch_id = gen_code_port()
    db["CHANNELS"][ch_id] = {"id": ch_id, "name": data['name'], "owner": code, "desc": "Nouvelle chaîne"}
    save_db(db)
    return jsonify({"status":"ok", "id": ch_id})

@app.route('/get_channels')
def get_channels():
    db = load_db()
    return jsonify(list(db["CHANNELS"].values()))

@socketio.on('join')
def on_join(data): join_room(data['code'])

@socketio.on('send_message')
def handle_send(data):
    db = load_db()
    cle = "-".join(sorted([data['to'], data['from']]))
    if cle not in db["MESSAGES"]: db["MESSAGES"][cle] = []
    db["MESSAGES"][cle].append(data)
    dest = data['to']; src = data['from']
    if dest not in db["UNREAD"]: db["UNREAD"][dest] = {}
    if src not in db["UNREAD"][dest]: db["UNREAD"][dest][src] = 0
    db["UNREAD"][dest][src] += 1
    save_db(db)
    emit('receive_message', data, room=dest)
    emit('new_message_alert', {}, room=dest)

if __name__=='__main__':
    socketio.run(app,host='0.0.0.0',port=10000)
