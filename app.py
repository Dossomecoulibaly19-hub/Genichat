from flask import Flask, render_template_string, request, redirect, session, url_for, jsonify, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room
import json, os, base64, time, random, string, threading
from datetime import datetime, timedelta # AJOUT POUR STATUT 24H
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
        return {"USERS": {}, "MESSAGES": {}, "UNREAD": {}, "ARCHIVED": {}, "CHANNELS": {}, "STATUS": {}, "CHANNEL_MSGS": {}} # AJOUT CHANNEL_MSGS

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
        if code not in db["USERS"] and code not in db["CHANNELS"]:
            return code

# AJOUT 1: NETTOYAGE STATUT 24H AUTO
def clean_status():
    db = load_db()
    now = datetime.now()
    for user_code in list(db["STATUS"].keys()):
        db["STATUS"][user_code] = [s for s in db["STATUS"][user_code] if datetime.fromisoformat(s['time']) > now - timedelta(hours=24)]
    save_db(db)
threading.Timer(3600, clean_status).start() # toutes les 1h

CSS = """* {box-sizing: border-box; margin:0; padding:0; font-family: 'Segoe UI', Roboto, sans-serif; -webkit-user-select:none; user-select:none;} /* AJOUT 2: bloque selection */
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
.crop-square {border-radius:0;} /* AJOUT POUR STATUT RECTANGLE */
.crop-img {position:absolute; cursor:grab; max-width:none; left:50%; top:50%; touch-action:none; user-select:none;}
.crop-buttons {position:absolute; bottom:0; width:100%; padding:15px; background:#202C33; display:flex; gap:10px;}
h2{text-align:center; margin-bottom:15px; color:#00A884;}
label {display:block; margin-top:5px; font-size:14px; color:#8696A0;}
.mic-btn{background:#00A884; border:none; border-radius:50%; width:48px; height:48px; font-size:22px; color:white; cursor:pointer; touch-action:none;} /* AJOUT 3: bloque menu copie */
.mic-btn.recording{background:red; animation: pulse 1s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,0,0,0.7)} 70%{box-shadow:0 0 0 10px rgba(255,0,0,0)} 100%{box-shadow:0 0 0 0 rgba(255,0,0,0)}}
.audio-player{width:200px; height:40px;}
.badge{background:#00A884; color:white; border-radius:50%; min-width:22px; height:22px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:bold; padding:2px 6px;}
.popup {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:100; justify-content:center; align-items:center;}
.popup-box {background:#202C33; padding:25px; border-radius:15px; width:90%; max-width:350px; text-align:center;}
.popup-buttons {display:flex; gap:10px; margin-top:20px;}
/* AJOUT 4: BARRE BAS + PAGES */
.bottom-nav{display:flex; background:#202C33; justify-content:space-around; padding:8px 0; position:sticky; bottom:0; z-index:20;}
.nav-item{flex:1; text-align:center; color:#8696A0; font-size:12px; cursor:pointer; padding:5px;}
.nav-item.active{color:#00A884;}
.nav-item span{font-size:22px; display:block;}
.page{display:none; flex:1; flex-direction:column; height:calc(100vh - 120px);}
.page.active{display:flex;}
.editor-video{padding:20px; text-align:center; color:#8696A0;}
.channel-card{background:#2A3942; padding:15px; margin:10px; border-radius:10px; display:flex; gap:10px; align-items:center;}
/* AJOUT 5: VIDEO EDITOR + STATUT */
.video-editor{padding:10px; text-align:center;}
.video-editor video{width:100%; max-height:60vh; background:#000;}
.video-slider{width:100%; margin:10px 0;}
.status-list{display:flex; flex-direction:column; padding:10px; gap:5px; overflow-y:auto;} /* MODIF POUR LISTE CONTACTS */
.status-contact{display:flex; align-items:center; gap:10px; padding:10px; background:#2A3942; border-radius:10px; cursor:pointer;}
.status-contact.avatar{border:3px solid #2A3942;}
.status-contact.has-status.avatar{border:3px solid #00A884;}
.status-preview{width:60px; height:90px; border-radius:8px; background-size:cover; background-position:center; margin-left:auto;}
.file-input-btn{display:inline-block; padding:10px; background:#2A3942; border-radius:10px; cursor:pointer; margin:5px;}
"""

# TES HTML LOGIN, REGISTER, SETTINGS RESTENT IDENTIQUES

CONTACTS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Chats</title><style>{{ CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
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

<div id="page-statut" class="page">
<div style="padding:10px;"><button class="btn" onclick="document.getElementById('statusFile').click()">+ Ajouter mon Statut</button></div>
<div class="status-list" id="statusList"></div>
<input type="file" id="statusFile" accept="image/*,video/*" style="display:none;">
</div>

<div id="page-chaines" class="page">
<div style="padding:10px;"><input id="searchChannel" class="input" placeholder="Recher une chaîne"><button class="btn" onclick="createChannel()">+ Créer ma chaîne</button></div>
<div id="channelsList" class="contact-list"></div>
</div>

<div id="page-actu" class="page"><div class="editor-video"><h3>Actualités IA</h3><p>Résumé de tes messages non lus. Désactivé pour le moment.</p></div></div>

<div class="bottom-nav">
<div class="nav-item active" onclick="showPage('contacts')"><span>💬</span>Accueil</div>
<div class="nav-item" onclick="showPage('statut')"><span>⭕</span>Statut</div>
<div class="nav-item" onclick="showPage('chaines')"><span>📢</span>Chaînes</div>
<div class="nav-item" onclick="showPage('actu')"><span>📰</span>Actu</div>
</div>

<!-- AJOUT 6: MODAL EDITEUR VIDEO -->
<div class="crop-modal" id="videoEditorModal">
<div class="video-editor">
<video id="videoPreview" controls></video>
<input type="text" id="statusText" class="input" placeholder="Écris un texte sur ton statut...">
<label>Début: <input type="range" id="videoSliderStart" class="video-slider" min="0" value="0" max="100"></label>
<label>Fin: <input type="range" id="videoSliderEnd" class="video-slider" min="0" value="100" max="100"></label>
<div class="crop-buttons">
<button class="btn btn-gray" onclick="closeVideoEditor()">Annuler</button>
<button class="btn" onclick="publishVideo()">OK Publier</button>
</div>
</div>
</div>

<!-- AJOUT 7: PAGE CHAINE CHAT -->
<div id="channelChatPage" class="page" style="display:none; height:100vh;">
<div class="header"><button onclick="backToChannels()" style="background:none; border:none; color:white; font-size:24px;">←</button>
<div class="avatar" id="channelAvatar"></div>
<div><b id="channelName"></b><br><small id="channelDesc" style="color:#8696A0;"></small></div></div>
<div class="messages" id="channelMsgBox"></div>
<div class="add-bar">
<label class="file-input-btn">📎<input type="file" id="channelFileInput" style="display:none;"></label>
<input type="text" id="channelMessage" placeholder="Écris un message" class="input">
<button class="btn" style="width:60px;" onclick="sendChannelMsg()">➤</button>
</div>
</div>

<div class="popup" id="deletePopup">
<div class="popup-box">
<h3>Supprimer le contact?</h3>
<p id="deleteText">Cette action va supprimer le contact et tous les messages.</p>
<div class="popup-buttons">
<button class="btn btn-gray" onclick="closePopup()">Annuler</button>
<button class="btn btn-danger" onclick="deleteConfirmed()">Supprimer</button>
</div>
</div>
</div>

<script>
const socket=io("{{ central }}"); const MY_CODE="{{ my_code }}";
let selectedContacts = []; let longPressTimer; let isSelecting = false;
let videoBase64 = null; let videoType, publishTarget; let currentChannel = null; // FIX: on garde le base64

socket.emit('join',{code:MY_CODE});

function showPage(page){
    document.querySelectorAll('.page').forEach(p=>p.style.display='none');
    document.querySelectorAll('.nav-item').forEach(p=>p.classList.remove('active'));
    document.getElementById('page-'+page).style.display='flex';
    event.currentTarget.classList.add('active');
    if(page=='chaines'){ loadChannels(); }
    if(page=='statut'){ loadAllStatus(); }
}

// AJOUT 8: EDITEUR VIDEO STATUT + CHAINE CORRIGE
document.getElementById('statusFile').onchange = e => openVideoEditor(e, 'status');
document.getElementById('channelFileInput').onchange = e => sendChannelFile(e);

function openVideoEditor(e, target){
    const file = e.target.files[0]; if(!file) return;
    publishTarget = target;
    videoType = file.type.startsWith('video')? 'video' : 'image';
    const reader = new FileReader();
    reader.onload = function(ev){
        videoBase64 = ev.target.result; // ON GARDE EN MEMOIRE
        if(videoType == 'video'){
            document.getElementById('videoPreview').src = ev.target.result;
            document.getElementById('videoSliderEnd').max = document.getElementById('videoPreview').duration || 100;
            document.getElementById('videoEditorModal').style.display='flex';
        }else{
            publishMedia(ev.target.result);
        }
    }
    reader.readAsDataURL(file);
}
function closeVideoEditor(){ document.getElementById('videoEditorModal').style.display='none'; document.getElementById('statusText').value=''; videoBase64=null; }
function publishVideo(){
    const start = document.getElementById('videoSliderStart').value;
    const end = document.getElementById('videoSliderEnd').value;
    const text = document.getElementById('statusText').value;
    if(!videoBase64) return;
    fetch('/publish_status', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({type:'video', data:videoBase64, start, end, text, target:publishTarget})}).then(r=>r.json()).then(()=>{closeVideoEditor(); loadAllStatus();})
}

function publishMedia(data){
    const text = document.getElementById('statusText').value;
    fetch('/publish_status', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({type:'image', data, text, target:publishTarget})}).then(r=>r.json()).then(()=>{loadAllStatus(); document.getElementById('statusText').value='';})
}

function loadAllStatus(){
    fetch('/get_all_status').then(r=>r.json()).then(data=>{
        let html='';
        data.forEach(user=>{
            let hasStatus = user.status.length > 0;
            let preview = hasStatus? user.status[0].data : '';
            html+=`<div class="status-contact ${hasStatus?'has-status':''}" onclick="viewStatus('${user.code}')">
                <div class="avatar" style="background-image:url('${user.photo}')">${user.photo?'':user.nom[0]}</div>
                <div class="contact-info"><b>${user.nom}</b><br><small>${hasStatus?'Voir statut':'Aucun statut'}</small></div>
                ${hasStatus?`<div class="status-preview" style="background-image:url(${preview})"></div>`:''}
            </div>`
        });
        document.getElementById('statusList').innerHTML=html || '<p style="padding:20px; text-align:center;">Ajoute des contacts pour voir leurs statuts</p>';
    })
}
function viewStatus(code){ alert('Ouverture des statuts de: '+code) }

function startLongPress(code){ longPressTimer = setTimeout(()=>{ enterSelectionMode(code); }, 600); }
function endLongPress(){ clearTimeout(longPressTimer); }
function enterSelectionMode(code){ isSelecting = true; selectContact(code); }
function selectContact(code){ const el = document.querySelector(`[data-code="${code}"]`); if(!el) return; if(selectedContacts.includes(code)){ selectedContacts = selectedContacts.filter(c=>c!=code); el.classList.remove('selected'); } else { selectedContacts.push(code); el.classList.add('selected'); } updateSelectionHeader(); }
function updateSelectionHeader(){ if(selectedContacts.length > 0){ document.getElementById('mainHeader').style.display='none'; document.getElementById('selectionHeader').style.display='flex'; document.getElementById('selectedCount').innerText = selectedContacts.length + ' sélectionné'; } }
function exitSelection(){ isSelecting = false; selectedContacts = []; document.querySelectorAll('.contact.selected').forEach(el=>el.classList.remove('selected')); document.getElementById('mainHeader').style.display='flex'; document.getElementById('selectionHeader').style.display='none'; }
function confirmDelete(){ document.getElementById('deleteText').innerText = `Supprimer ${selectedContacts.length} contact(s) et tous leurs messages?`; document.getElementById('deletePopup').style.display='flex'; }
function closePopup(){ document.getElementById('deletePopup').style.display='none'; }
function deleteConfirmed(){ fetch('/delete_contacts', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({contacts: selectedContacts})}).then(()=>{ location.reload(); }); }
function archiveSelected(){ fetch('/archive_contacts', {method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({contacts: selectedContacts})}).then(()=>{ location.reload(); }); }

function loadChannels(){ fetch('/get_channels').then(r=>r.json()).then(data=>{ let html=''; data.forEach(ch=>{ html+=`<div class="channel-card" onclick="openChannel('${ch.id}')"><div class="avatar">${ch.name[0]}</div><div><b>${ch.name}</b><br><small>${ch.desc}</small></div></div>` }); document.getElementById('channelsList').innerHTML=html || '<p style="text-align:center; padding:20px;">Aucune chaîne</p>'; }) }
function createChannel(){ let name=prompt("Nom de ta chaîne:"); if(name){ fetch('/create_channel', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name})}).then(r=>r.json()).then(res=>{ if(res.status=='ok'){ openChannel(res.id); } }) } }

function openChannel(id){
    currentChannel = id;
    document.querySelectorAll('.page').forEach(p=>p.style.display='none');
    document.getElementById('channelChatPage').style.display='flex';
    fetch('/get_channel/'+id).then(r=>r.json()).then(ch=>{
        document.getElementById('channelName').innerText = ch.name;
        document.getElementById('channelDesc').innerText = ch.desc;
        document.getElementById('channelAvatar').innerText = ch.name[0];
        loadChannelMsgs(id);
    })
}
function backToChannels(){ document.getElementById('channelChatPage').style.display='none'; document.getElementById('page-chaines').style.display='flex'; currentChannel=null; }

function loadChannelMsgs(id){
    fetch('/get_channel_msgs/'+id).then(r=>r.json()).then(msgs=>{
        let box = document.getElementById('channelMsgBox'); box.innerHTML='';
        msgs.forEach(m=>{
            let d=document.createElement('div'); d.className='msg '+(m.from==MY_CODE?'me':'you');
            let content = m.type=='text'? m.msg : `<a href="${m.msg}" target="_blank">📎 Fichier</a>`;
            d.innerHTML=`<b>${m.from_nom}</b><br>${content}<div class="time">${m.time}</div>`;
            box.append(d);
        });
        box.scrollTop = box.scrollHeight;
    })
}
function sendChannelMsg(){
    const msg = document.getElementById('channelMessage').value; if(!msg ||!currentChannel) return;
    fetch('/send_channel_msg', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({channel:currentChannel, msg, type:'text'})}).then(()=>{document.getElementById('channelMessage').value=''; loadChannelMsgs(currentChannel);})
}
function sendChannelFile(e){
    const file = e.target.files[0]; if(!file ||!currentChannel) return;
    const reader = new FileReader();
    reader.onload = function(ev){
        fetch('/send_channel_msg', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({channel:currentChannel, msg:ev.target.result, type:'file'})}).then(()=>{loadChannelMsgs(currentChannel);})
    }
    reader.readAsDataURL(file);
}

document.querySelectorAll('.contact').forEach(el=>{ el.addEventListener('click', ()=>{ if(!isSelecting){ location.href='/chat/'+el.dataset.code; } else { selectContact(el.dataset.code); } }); });

// AJOUT 9: SYNC ARRIERE PLAN POUR L'APP
function sendToApp(data){ if(window.Android){ Android.saveMessage(JSON.stringify(data)); } }
function syncMessages(){ {% for c in contacts %} fetch('/get_msg/{{ c }}').then(r=>r.json()).then(msgs=>{ localStorage.setItem('chat_{{ my_code }}_{{ c }}', JSON.stringify(msgs)); msgs.forEach(m => sendToApp({contact:'{{ c }}', message:m.msg, heure:m.time, envoyeur:m.from})); }); {% endfor %} }
syncMessages(); socket.on('new_message_alert', ()=>{ syncMessages(); });
</script>
</body></html>"""

ARCHIVES_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Archives</title><style>{{ CSS }}</style></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><a href="/contacts" style="color:white; font-size:24px;">←</a><h2>Archives</h2><div></div></div>
<div class="contact-list" id="contact-list">{% for c in archived %}
<div class="contact" onclick="location='/chat/{{ c }}'">
<div class="avatar" style="background-image:url('{{ users[c].photo }}')">{{ '' if users[c].photo else users[c].nom[0]|upper }}</div>
<div class="contact-info"><b>{{ users[c].nom }}</b><br><small style="color:#8696A0;">{{ c }}</small></div>
</div>{% endfor %}</div>
</body></html>"""

CHAT_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chat avec {{ ami.nom }}</title><style>{{ CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><a href="/contacts" style="color:white; font-size:24px;">←</a>
<div class="avatar" style="background-image:url('{{ ami.photo }}')">{{ '' if ami.photo else ami.nom[0]|upper }}</div>
<div><b>{{ ami.nom }}</b><br><small style="color:#8696A0;">{{ code_ami }}</small></div></div>
<div class="messages" id="msgBox"></div>
<form class="send-box" id="sendForm">
<input type="text" id="message" placeholder="Écris un message" class="input">
<button id="micBtn" type="button" class="mic-btn">🎤</button>
<button id="sendBtn" class="btn" style="border-radius:50%; width:48px; height:48px; padding:0; font-size:20px; display:none;">➤</button></form>
<script>
const socket=io("{{ central }}");const MY_CODE="{{ my_code }}";const AMI_CODE="{{ code_ami }}";
const STORAGE_KEY = `chat_${MY_CODE}_${AMI_CODE}`;
let mediaRecorder, audioChunks = [];
const micBtn = document.getElementById('micBtn');
const sendBtn = document.getElementById('sendBtn');
const msgInput = document.getElementById('message');

socket.on('connect',()=>socket.emit('join',{code:MY_CODE}));

function sendToApp(data){
  if(window.Android){
    Android.saveMessage(JSON.stringify({
      contact: AMI_CODE,
      message: data.msg,
      heure: data.time,
      envoyeur: data.from
    }));
  }
}

function saveLocal(msgs){ localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs)); }
function loadLocal(){ return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }

function render(msgs){
  document.getElementById('msgBox').innerHTML='';
  msgs.forEach(m=>addMsg(m.from_nom,m.msg,m.from==MY_CODE,m.time,m.status,m.id,m.type));
  scroll();
}

function load(){
  let localMsgs = loadLocal();
  if(localMsgs.length > 0) render(localMsgs);
  fetch('/get_msg/'+AMI_CODE).then(r=>r.json()).then(serverMsgs=>{
    if(JSON.stringify(serverMsgs)!== JSON.stringify(localMsgs)){
      saveLocal(serverMsgs);
      serverMsgs.forEach(m => sendToApp(m));
      render(serverMsgs);
    }
  }).catch(()=>{});
}
load();

function sendData(data){
  let local = loadLocal(); local.push(data); saveLocal(local);
  sendToApp(data);
  addMsg(data.from_nom,data.msg,true,data.time,data.status,data.id,data.type); scroll();
  socket.emit('send_message',data);
}

sendBtn.onclick=e=>{e.preventDefault();const msg=msgInput.value;if(!msg)return;
let t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});let id='m'+Date.now();
let data={to:AMI_CODE,from:MY_CODE,from_nom:"{{ my_nom }}",msg:msg,time:t,id:id,type:'text',status:'sent'};
sendData(data);
msgInput.value='';sendBtn.style.display='none';micBtn.style.display='block';}

msgInput.oninput=()=>{sendBtn.style.display=msgInput.value?'block':'none'; micBtn.style.display=msgInput.value?'none':'block';}

micBtn.onmousedown=micBtn.ontouchstart=async()=>{
  micBtn.classList.add('recording');
  const stream = await navigator.mediaDevices.getUserMedia({audio:true});
  mediaRecorder = new MediaRecorder(stream, {mimeType: 'audio/webm'});
  audioChunks = [];
  mediaRecorder.ondataavailable=e=>audioChunks.push(e.data);
  mediaRecorder.onstop=()=>{
    const audioBlob = new Blob(audioChunks,{type:'audio/webm'});
    const reader = new FileReader();
    reader.onloadend=()=>{
      const base64Audio = reader.result;
      let t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});let id='m'+Date.now();
      let data={to:AMI_CODE,from:MY_CODE,from_nom:"{{ my_nom }}",msg:base64Audio,time:t,id:id,type:'audio',status:'sent'};
      sendData(data);
    }
    reader.readAsDataURL(audioBlob);
  }
  mediaRecorder.start();
}
micBtn.onmouseup=micBtn.ontouchend=()=>{
  if(mediaRecorder && mediaRecorder.state!='inactive'){mediaRecorder.stop();}
  micBtn.classList.remove('recording');
}

function addMsg(from,msg,me,time,status,id,type='text'){
  let d=document.createElement('div');d.id=id;d.className='msg '+(me?'me':'you');
  let check = me? (status=='read'?'<span class="check blue">✓</span>':'<span class="check gray">✓</span>') : '';
  let content = type=='audio'? `<audio controls class="audio-player" src="${msg}"></audio>` : msg;
  d.innerHTML=`${content}<div class="time">${time} ${check}</div>`;document.getElementById('msgBox').append(d);
}
function scroll(){let box=document.getElementById('msgBox');box.scrollTop=box.scrollHeight;}
socket.on('receive_message',d=>{
    if(d.from==AMI_CODE){
      let local = loadLocal(); local.push(d); saveLocal(local);
      sendToApp(d);
      addMsg(d.from_nom,d.msg,false,d.time,'read',d.id,d.type);scroll();
    }
});
</script></body></html>"""

def get_user():
    code = session.get('code')
    db = load_db()
    return code, db["USERS"].get(code), db

# TOUTES TES ROUTES JUSQU'A get_msg RESTENT IDENTIQUES

@app.route('/get_all_status')
def get_all_status():
    code, user, db = get_user()
    if not code: return jsonify([])
    clean_status()
    result = []
    for c in user['contacts']:
        if c in db["USERS"]:
            result.append({
                "code": c,
                "nom": db["USERS"][c]['nom'],
                "photo": db["USERS"][c]['photo'],
                "status": db["STATUS"].get(c, [])
            })
    return jsonify(result)

@app.route('/publish_status', methods=['POST'])
def publish_status():
    code, user, db = get_user()
    if not code: return jsonify({"status":"error"}), 403
    data = request.json
    if code not in db["STATUS"]: db["STATUS"][code] = []
    db["STATUS"][code].append({"type": data['type'], "data": data['data'], "time": datetime.now().isoformat(), "text": data.get('text','')})
    save_db(db)
    return jsonify({"status":"ok"})

@app.route('/create_channel', methods=['POST'])
def create_channel():
    code, user, db = get_user()
    if not code: return jsonify({"status":"error"}), 403
    data = request.json
    ch_id = gen_code_port()
    db["CHANNELS"][ch_id] = {"id": ch_id, "name": data['name'], "owner": code, "desc": "Description de la chaîne"}
    if ch_id not in db["CHANNEL_MSGS"]: db["CHANNEL_MSGS"][ch_id] = []
    save_db(db)
    return jsonify({"status":"ok", "id": ch_id})

@app.route('/get_channels')
def get_channels():
    code, user, db = get_user()
    return jsonify(list(db["CHANNELS"].values()))

@app.route('/get_channel/<ch_id>')
def get_channel(ch_id):
    db = load_db()
    return jsonify(db["CHANNELS"].get(ch_id, {}))

@app.route('/get_channel_msgs/<ch_id>')
def get_channel_msgs(ch_id):
    db = load_db()
    return jsonify(db["CHANNEL_MSGS"].get(ch_id, []))

@app.route('/send_channel_msg', methods=['POST'])
def send_channel_msg():
    code, user, db = get_user()
    if not code: return jsonify({"status":"error"}), 403
    data = request.json
    ch_id = data['channel']
    if ch_id not in db["CHANNEL_MSGS"]: db["CHANNEL_MSGS"][ch_id] = []
    db["CHANNEL_MSGS"][ch_id].append({
        "from": code,
        "from_nom": user['nom'],
        "msg": data['msg'],
        "type": data['type'],
        "time": datetime.now().strftime("%H:%M")
    })
    save_db(db)
    return jsonify({"status":"ok"})

@socketio.on('join')
def on_join(data): join_room(data['code'])

@socketio.on('send_message')
def handle_send(data):
    db = load_db()
    cle = "-".join(sorted([data['to'], data['from']]))
    if cle not in db["MESSAGES"]: db["MESSAGES"][cle] = []
    db["MESSAGES"][cle].append(data)

    dest = data['to']
    src = data['from']
    if dest not in db["UNREAD"]: db["UNREAD"][dest] = {}
    if src not in db["UNREAD"][dest]: db["UNREAD"][dest][src] = 0
    db["UNREAD"][dest][src] += 1

    save_db(db)

    emit('receive_message', data, room=dest)
    emit('new_message_alert', {}, room=dest)

if __name__=='__main__':
    port = int(os.environ.get("PORT", 10000)) # MODIF POUR RENDER
    socketio.run(app,host='0.0.0.0',port=port)
