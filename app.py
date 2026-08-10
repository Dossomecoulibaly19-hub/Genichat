import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template_string, request, redirect, session, url_for, jsonify, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room
import json, os, base64, time, random, string, threading
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = "genie_v33_whatsapp_dossome"
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # Règle: Support jusqu'à 200MB de vidéo/image/statut
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', max_http_buffer_size=200*1024*1024)

CENTRAL_SERVER = "https://genie-facteur.onrender.com"
DB_FILE = "genie_db.json"
db_lock = threading.Lock()

def load_db():
    with db_lock:
        if os.path.exists(DB_FILE):
            try:
                with open(DB_FILE) as f: db = json.load(f)
            except: db = {}
        else:
            db = {}
        
        if "USERS" not in db: db["USERS"] = {}
        if "MESSAGES" not in db: db["MESSAGES"] = {}
        if "UNREAD" not in db: db["UNREAD"] = {}
        if "ARCHIVED" not in db: db["ARCHIVED"] = {}
        if "SETTINGS" not in db: db["SETTINGS"] = {}
        if "GROUPS" not in db: db["GROUPS"] = {}
        if "GROUP_MSGS" not in db: db["GROUP_MSGS"] = {}
        if "STATUSES" not in db: db["STATUSES"] = {}
        if "STATUS_COMMENTS" not in db: db["STATUS_COMMENTS"] = {}
        if "CHANNELS" not in db: db["CHANNELS"] = {}
        if "CHANNEL_MSGS" not in db: db["CHANNEL_MSGS"] = {}
        
        return db

def save_db(db):
    def _save():
        try:
            with db_lock:
                tmp = DB_FILE + ".tmp"
                with open(tmp, "w") as f: json.dump(db, f, separators=(',', ':'))
                os.replace(tmp, DB_FILE)
        except Exception as e:
            print("Erreur save:", e)
    threading.Thread(target=_save, daemon=True).start()

def gen_code_port():
    db = load_db()
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in db["USERS"] and code not in db["GROUPS"] and code not in db["CHANNELS"]:
            return code

def cleanup_statuses(db):
    now = time.time()
    twenty_four_hours = 24 * 3600
    modified = False
    for status_id in list(db["STATUSES"].keys()):
        status = db["STATUSES"][status_id]
        if now - status.get("timestamp", 0) > twenty_four_hours:
            del db["STATUSES"][status_id]
            if status_id in db["STATUS_COMMENTS"]:
                del db["STATUS_COMMENTS"][status_id]
            modified = True
    if modified:
        save_db(db)

def get_theme_css(theme):
    if theme == "blanc":
        return "body{background:#F0F2F5; color:#111B21;}.header{background:#FFFFFF; color:#111B21;}.box{background:#FFFFFF;}.input{background:#F0F2F5; color:#111B21;}.btn-gray{background:#E9EDEF; color:#111B21;}.messages{background:#E5DDD5;}.msg.you{background:#FFFFFF; color:#111B21;}.send-box{background:#F0F2F5;}.add-bar{background:#F0F2F5;}"
    else:
        return "body{background:#111B21; color:#E9EDEF;}"

CSS_BASE = """* {box-sizing: border-box; margin:0; padding:0; font-family: 'Segoe UI', Roboto, sans-serif; -webkit-user-select:none; user-select:none;}
.header {padding:12px 16px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; background:#202C33;}
.header-actions{display:flex; gap:15px; align-items:center;}
.btn {background:#00A884; color:white; border:none; padding:14px 15px; border-radius:10px; cursor:pointer; font-weight:600; width:100%; margin-top:12px; font-size:16px; text-decoration:none; display:block; text-align:center;}
.btn-danger {background:#D93025;}
.btn-gray {background:#2A3942; color:white;}
.input {padding:14px; border:none; border-radius:10px; width:100%; margin-top:6px; font-size:16px; background:#2A3942; color:white;}
.form-group {margin-bottom:15px;}
.avatar {width:40px; height:40px; border-radius:50%; background:#00A884; display:flex; align-items:center; justify-content:center; font-weight:bold; background-size:cover; background-position:center; color:white; cursor:pointer;}
.avatar-big {width:150px; height:150px; border-radius:50%; margin:0 auto 20px; display:flex; align-items:center; justify-content:center; background:#2A3942; font-size:60px; font-weight:bold; border:4px solid #00A884; background-size:cover; background-position:center; color:white; overflow:hidden;}
.box {padding:25px; border-radius:20px; max-width:450px; margin:30px auto; width:90%; box-shadow:0 4px 20px rgba(0,0,0,0.3); background:#202C33;}
.code-info {padding:14px; background:#000; font-size:20px; color:#00A884; border-radius:10px; text-align:center; letter-spacing:4px; font-weight:bold; margin:10px 0; user-select:all;}
.contact-list {flex:1; overflow-y:auto;}
.contact{padding:14px 16px; display:flex; align-items:center; gap:14px; cursor:pointer; border-bottom:1px solid #2A3942; position:relative; user-select:none;}
.contact.selected{background:#2A3942;}
.contact:hover{background:#2A3942;}
.contact-info{flex:1;}
.add-bar{padding:10px; display:flex; gap:10px; position:sticky; bottom:0; background:#111B21;}
.messages{padding:15px; flex:1; overflow-y:auto; display:flex; flex-direction:column; background-size:cover; background-position:center;}
.msg{padding:9px 13px; border-radius:8px; margin:5px 0; max-width:78%; font-size:15px; position:relative;}
.msg.me{background:#005C4B; align-self:flex-end; border-bottom-right-radius:2px; color:white;}
.msg.you{background:#202C33; align-self:flex-start; border-bottom-left-radius:2px;}
.time{font-size:11px; color:#8696A0; text-align:right; margin-top:4px;}
.send-box{display:flex; padding:10px; gap:10px; align-items:center; position:sticky; bottom:0; z-index:5; background:#202C33;}
.check.gray{color:#8696A0;}.check.blue{color:#53BDEB;}
.alert{background:#00A884; padding:12px; border-radius:10px; margin-bottom:15px; text-align:center; font-weight:600;}
.crop-modal {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:#000; z-index:99; flex-direction:column; justify-content:center; align-items:center;}
.crop-area {position:relative; width:100%; height:100%; display:flex; justify-content:center; align-items:center; overflow:hidden; touch-action:none;}
.crop-circle {position:absolute; width:220px; height:220px; border:4px solid #00A884; border-radius:50%; box-shadow:0 0 0 9999px rgba(0,0,0,0.8); pointer-events:none;}
.crop-square {position:absolute; width:280px; height:280px; border:4px solid #00A884; box-shadow:0 0 0 9999px rgba(0,0,0,0.8); pointer-events:none;}
.crop-img {position:absolute; cursor:grab; max-width:none; left:50%; top:50%; touch-action:none; user-select:none;}
.crop-buttons {position:absolute; bottom:0; width:100%; padding:15px; background:#202C33; display:flex; gap:10px; justify-content:center; z-index:100;}
h2{text-align:center; margin-bottom:15px; color:#00A884;}
label {display:block; margin-top:5px; font-size:14px; color:#8696A0;}
.mic-btn,.file-btn{background:#00A884; border:none; border-radius:50%; width:48px; height:48px; font-size:22px; color:white; cursor:pointer; display:flex; align-items:center; justify-content:center;}
.mic-btn.recording{background:red; animation: pulse 1s infinite;}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,0,0,0.7)} 70%{box-shadow:0 0 0 10px rgba(255,0,0,0)} 100%{box-shadow:0 0 0 0 rgba(255,0,0,0)}}
.audio-player{width:200px; height:40px; max-width:100%;}
.badge{background:#00A884; color:white; border-radius:50%; min-width:22px; height:22px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:bold; padding:2px 6px;}
.popup {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); z-index:100; justify-content:center; align-items:center;}
.popup-box {background:#202C33; padding:25px; border-radius:15px; width:90%; max-width:400px; text-align:center; max-height:90vh; overflow-y:auto;}
.popup-buttons {display:flex; gap:10px; margin-top:20px;}
.media-viewer {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.95); z-index:101; justify-content:center; align-items:center; flex-direction:column; padding:20px;}
.media-viewer img,.media-viewer video {max-width:100%; max-height:80vh; object-fit:contain; border-radius:8px;}
.media-actions {position:absolute; bottom:30px; display:flex; gap:15px; z-index:102;}
.context-menu {display:none; position:absolute; background:#2A3942; border-radius:8px; padding:5px 0; z-index:50; min-width:180px;}
.context-menu button {width:100%; padding:12px 15px; background:none; border:none; color:white; text-align:left; cursor:pointer;}
.context-menu button:hover {background:#344854;}
.chat-img {max-width:220px; max-height:220px; object-fit:cover; border-radius:8px; cursor:pointer; margin-top:4px;}
.chat-video {max-width:220px; max-height:220px; border-radius:8px; cursor:pointer; margin-top:4px;}

.nav-tabs {display:flex; background:#202C33; border-bottom:1px solid #2A3942; position:sticky; top:60px; z-index:9;}
.tab-item {flex:1; padding:12px; text-align:center; color:#8696A0; text-decoration:none; font-weight:bold; font-size:14px; border-bottom:3px solid transparent;}
.tab-item.active {color:#00A884; border-bottom:3px solid #00A884;}
.tiktok-container {height:100vh; overflow-y:scroll; snap-type:y mandatory; scroll-snap-type:y mandatory; background:#000;}
.tiktok-slide {height:100vh; width:100vw; snap-align:start; scroll-snap-align:start; position:relative; display:flex; justify-content:center; align-items:center;}
.tiktok-media {max-width:100%; max-height:100%; object-fit:contain;}
.tiktok-overlay {position:absolute; bottom:20px; left:20px; right:20px; color:white; text-shadow:0 1px 3px rgba(0,0,0,0.8);}

/* SIMULATION PHONE FRAME (FONDS D'ECRAN) */
.phone-sim-container {width: 220px; height: 380px; border: 4px solid #00A884; border-radius: 25px; overflow: hidden; position: relative; margin: 10px auto; background: #111B21; box-shadow: 0 0 15px rgba(0,0,0,0.5);}
.phone-sim-screen {width: 100%; height: 100%; position: relative; overflow: hidden;}
.phone-sim-chat {position: absolute; top:0; left:0; width:100%; height:100%; z-index:2; pointer-events:none; display:flex; flex-direction:column; justify-content:space-between; padding:10px;}
.phone-sim-header {background:rgba(32,44,51,0.9); padding:5px 8px; border-radius:8px; color:white; font-size:10px;}
.phone-sim-msg {padding:5px 8px; border-radius:6px; font-size:9px; max-width:70%; margin:3px 0;}
.phone-sim-msg.me {background:#005C4B; color:white; align-self:flex-end;}
.phone-sim-msg.you {background:#202C33; color:white; align-self:flex-start;}

/* AUDIO CUTTER INTERFACE */
.audio-range-box {background:#202C33; padding:10px; border-radius:10px; margin-top:10px; width:100%; text-align:center;}
.audio-slider-container {position:relative; width:100%; height:30px; margin:10px 0;}
"""

def avatar_letter(nom):
    return nom[0].upper() if nom else "?"

def get_user_settings(code, db):
    if code not in db["SETTINGS"]: db["SETTINGS"][code] = {"theme": "noir", "chat_bg": "", "group_bg": {}}
    return db["SETTINGS"][code]

LOGIN_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GenieChat</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style></head><body>
<div class="box">
<div style="display:flex; justify-content:space-between; align-items:center;">
    <h2>👋 GenieChat</h2>
    <button class="btn btn-gray" style="width:auto; padding:6px 12px; margin:0;" onclick="openHelpModal()">❓ AIDE</button>
</div>
{% if code and nom %}
<div class="alert">Bienvenue {{nom}}</div><label>TON CODE:</label><div class="code-info">{{ code }}</div>
<a href="/contacts" class="btn">Accéder aux Chats</a>
<a href="/logout" class="btn btn-gray">Changer de Compte</a>
{% else %}
<form method="POST" action="/login">
<div class="form-group"><label>Code Unique</label><input name="code" class="input" placeholder="Entre ton code" required></div>
<button class="btn">Se Connecter</button>
</form>
<p style="text-align:center; margin-top:15px; color:#8696A0;">Pas de compte? Crée en un <a href="/register" style="color:#00A884;">ici</a></p>
{% endif %}
</div>

<!-- Modal AIDE -->
<div class="popup" id="helpModal">
<div class="popup-box" style="text-align:left;">
    <h3>ℹ️ Guide & Info GenieChat</h3>
    <div style="max-height:300px; overflow-y:auto; font-size:14px; margin-top:15px; color:#E9EDEF; line-height:1.5;">
        <p><b>Bienvenue sur GenieChat !</b></p><br>
        <p>Cette application vous permet de communiquer de manière fluide, sécurisée et ultra-rapide sans aucune contrainte de carte SIM.</p><br>
        <p><b>Fonctionnalités principales :</b></p>
        <ul style="margin-left:20px;">
            <li>💬 <b>Chat Privé :</b> Échangez des messages, vocaux, photos et vidéos. Historique sauvegardé en sécurité.</li>
            <li>👥 <b>Groupes Directs :</b> Créez des groupes d'échange depuis vos contacts en un clic avec profils personnalisés.</li>
            <li>⭕ <b>Statuts :</b> Partagez des médias (jusqu'à 200 Mo), recadrez vos photos et intégrez vos musiques préférées avec découpage audio personnalisé !</li>
            <li>📢 <b>Chaînes :</b> Créez ou suivez des chaînes d'information publiques.</li>
            <li>🖼️ <b>Fonds Personnalisés :</b> Modifiez le fond de vos discussions grâce à notre simulateur interactif.</li>
        </ul><br>
        <p style="border-top:1px solid #2A3942; padding-top:10px;"><b>Information Créateur :</b></p>
        <p>Ce site et application ont été conçus et développés avec passion par <b>Dossomé Coulibaly</b> dans le but d'aider les gens à se connecter facilement, rapidement et sans restrictions de carte SIM.</p>
        <p>Besoin d'aide ou support ? Contact direct : <a href="mailto:kikicoulibaly19@gmail.com" style="color:#00A884;">kikicoulibaly19@gmail.com</a></p>
    </div>
    <button class="btn" style="margin-top:15px;" onclick="closeHelpModal()">J'ai compris</button>
</div>
</div>

<script>
function openHelpModal(){ document.getElementById('helpModal').style.display='flex'; }
function closeHelpModal(){ document.getElementById('helpModal').style.display='none'; }
</script>
</body></html>"""

REGISTER_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Créer Compte</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style></head><body>
<div class="box"><h2>Créer ton Compte</h2>
<form method="POST" action="/register" enctype="multipart/form-data">
<div id="preview" class="avatar-big"></div>
<label for="photo" class="btn btn-gray">📷 Choisir Photo Profil</label><input type="file" id="photo" name="photo" accept="image/*" style="display:none;">
<input type="hidden" id="crop_x" name="crop_x"><input type="hidden" id="crop_y" name="crop_y"><input type="hidden" id="crop_scale" name="crop_scale"><input type="hidden" id="original_img" name="original_img">
<div class="form-group"><label>Nom d'utilisateur</label><input name="nom" class="input" placeholder="Ton nom" required></div>
<button class="btn">Créer et Entrer</button>
</form><a href="/" class="btn btn-gray">Déjà un compte?</a>
</div>
<div id="cropModal" class="crop-modal"><div class="crop-area"><img id="cropImg" class="crop-img"><div class="crop-circle"></div></div>
<div class="crop-buttons"><button type="button" class="btn btn-gray" onclick="zoom(-0.1)">-</button>
<button type="button" class="btn btn-gray" onclick="closeCrop()">Annuler</button>
<button type="button" class="btn btn-gray" onclick="zoom(0.1)">+</button>
<button type="button" class="btn" onclick="saveCrop()">Valider</button></div></div>
<script>
let scale=1,posX=0,posY=0,isDragging=false; let startX=0,startY=0;
let cropImg = document.getElementById('cropImg'); let preview = document.getElementById('preview');
document.getElementById('photo').onchange = function(e){
    const file=e.target.files[0]; if(!file) return;
    const reader=new FileReader();
    reader.onload=function(ev){
        cropImg.src = ev.target.result;
        document.getElementById('original_img').value = ev.target.result;
        document.getElementById('cropModal').style.display='flex';
        scale=0.8; posX=0; posY=0; updateTransform();
    }
    reader.readAsDataURL(file);
}
function updateTransform(){cropImg.style.transform=`translate(-50%,-50%) translate(${posX}px,${posY}px) scale(${scale})`;}
cropImg.addEventListener('pointerdown', e=>{ e.preventDefault(); isDragging=true; let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; startX = pos.x - posX; startY = pos.y - posY; })
document.addEventListener('pointermove', e=>{ if(!isDragging) return; e.preventDefault(); let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; posX = pos.x - startX; posY = pos.y - startY; updateTransform(); })
document.addEventListener('pointerup', ()=>{ isDragging=false; })
function zoom(v){scale+=v; if(scale<0.3)scale=0.3; if(scale>3)scale=3; updateTransform();}
function closeCrop(){document.getElementById('cropModal').style.display='none';}
function saveCrop(){
    document.getElementById('crop_x').value=posX;
    document.getElementById('crop_y').value=posY;
    document.getElementById('crop_scale').value=scale;
    preview.style.backgroundImage = `url(${cropImg.src})`;
    preview.innerHTML = '';
    closeCrop();
}
</script></body></html>"""

SETTINGS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paramètres</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style></head><body>
<div class="header"><a href="/contacts" style="color:inherit; font-size:24px;">←</a><h2>Profil & Paramètres</h2><div></div></div>
<div class="box">
<label>TON CODE:</label><div class="code-info" onclick="navigator.clipboard.writeText('{{ code }}')"> {{ code }} </div><small style="color:#8696A0;">Clique pour copier</small>
<form method="POST" action="/update_profile" enctype="multipart/form-data">
<div id="preview" class="avatar-big" style="background-image:url('{{ photo }}')">{{ initial }}</div>
<label for="photo" class="btn btn-gray">📷 Changer Photo</label><input type="file" id="photo" name="photo" accept="image/*" style="display:none;">
<input type="hidden" id="crop_x" name="crop_x"><input type="hidden" id="crop_y" name="crop_y"><input type="hidden" id="crop_scale" name="crop_scale"><input type="hidden" id="original_img" name="original_img">
<div class="form-group"><label>Nom d'utilisateur</label><input name="nom" value="{{ nom }}" class="input" required></div>
<button class="btn">Enregistrer Profil</button>
</form>

<form method="POST" action="/update_theme">
<div class="form-group"><label>Fond du Site</label>
<select name="theme" class="input"><option value="noir" {% if theme=='noir' %}selected{% endif %}>Noir</option><option value="blanc" {% if theme=='blanc' %}selected{% endif %}>Blanc</option></select></div>
<button class="btn btn-gray">Changer Fond Site</button>
</form>

<button class="btn btn-gray" onclick="openChatBgModal()">🖼️ Changer Fond Discussion (Simulateur)</button>

</div>

<!-- Modal simulation recadrage fond d'écran de chat -->
<div class="crop-modal" id="chatBgModal">
<h3 style="color:white; margin-top:15px; position:absolute; top:10px; z-index:105;">Cadrage Fond Discussion</h3>
<div class="phone-sim-container">
    <div class="phone-sim-screen" id="simArea">
        <img id="bgCropImg" style="position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); max-width:none; touch-action:none; cursor:grab;">
        <div class="phone-sim-chat">
            <div class="phone-sim-header">Ami GenieChat</div>
            <div>
                <div class="phone-sim-msg you">Salut ! Test cadrage</div>
                <div class="phone-sim-msg me">Parfait 👍</div>
            </div>
        </div>
    </div>
</div>
<input type="file" id="bgFileInput" accept="image/*" style="display:none;" onchange="handleBgSelect(event)">
<div class="crop-buttons">
    <button type="button" class="btn btn-gray" onclick="document.getElementById('bgFileInput').click()">📁 Choisir</button>
    <button type="button" class="btn btn-gray" onclick="bgZoom(-0.1)">-</button>
    <button type="button" class="btn btn-gray" onclick="bgZoom(0.1)">+</button>
    <button type="button" class="btn btn-gray" onclick="closeChatBgModal()">Annuler</button>
    <button type="button" class="btn" onclick="saveChatBg()">Valider</button>
</div>
</div>

<div id="cropModal" class="crop-modal"><div class="crop-area"><img id="cropImg" class="crop-img"><div class="crop-circle"></div></div>
<div class="crop-buttons"><button type="button" class="btn btn-gray" onclick="zoom(-0.1)">-</button>
<button type="button" class="btn btn-gray" onclick="closeCrop()">Annuler</button>
<button type="button" class="btn btn-gray" onclick="zoom(0.1)">+</button>
<button type="button" class="btn" onclick="saveCrop()">Valider</button></div></div>

<script>
let scale=1,posX=0,posY=0,isDragging=false; let startX=0,startY=0;
let cropImg = document.getElementById('cropImg'); let preview = document.getElementById('preview');

document.getElementById('photo').onchange = function(e){
    const file=e.target.files[0]; if(!file) return;
    const reader=new FileReader();
    reader.onload=function(ev){
        cropImg.src = ev.target.result;
        document.getElementById('original_img').value = ev.target.result;
        document.getElementById('cropModal').style.display='flex';
        scale=0.8; posX=0; posY=0; updateTransform();
    }
    reader.readAsDataURL(file);
}
function updateTransform(){cropImg.style.transform=`translate(-50%,-50%) translate(${posX}px,${posY}px) scale(${scale})`;}
cropImg.addEventListener('pointerdown', e=>{ e.preventDefault(); isDragging=true; let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; startX = pos.x - posX; startY = pos.y - posY; })
document.addEventListener('pointermove', e=>{ if(!isDragging) return; e.preventDefault(); let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; posX = pos.x - startX; posY = pos.y - startY; updateTransform(); })
document.addEventListener('pointerup', ()=>{ isDragging=false; })
function zoom(v){scale+=v; if(scale<0.3)scale=0.3; if(scale>3)scale=3; updateTransform();}
function closeCrop(){document.getElementById('cropModal').style.display='none';}
function saveCrop(){
    document.getElementById('crop_x').value=posX; document.getElementById('crop_y').value=posY; document.getElementById('crop_scale').value=scale;
    preview.style.backgroundImage = `url(${cropImg.src})`; preview.innerHTML = ''; closeCrop();
}

/* Simulation fond de chat */
let bgScale=1, bgX=0, bgY=0, bgDragging=false, bgStartX=0, bgStartY=0;
const bgImg = document.getElementById('bgCropImg');
function openChatBgModal(){ document.getElementById('chatBgModal').style.display='flex'; }
function closeChatBgModal(){ document.getElementById('chatBgModal').style.display='none'; }
function handleBgSelect(e){
    const file = e.target.files[0]; if(!file) return;
    const reader = new FileReader();
    reader.onload = ev => { bgImg.src = ev.target.result; bgScale=1; bgX=0; bgY=0; updateBgTransform(); };
    reader.readAsDataURL(file);
}
function updateBgTransform(){ bgImg.style.transform = `translate(-50%,-50%) translate(${bgX}px,${bgY}px) scale(${bgScale})`; }
function bgZoom(v){ bgScale += v; if(bgScale<0.2) bgScale=0.2; updateBgTransform(); }
bgImg.addEventListener('pointerdown', e=>{ e.preventDefault(); bgDragging=true; let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; bgStartX = pos.x - bgX; bgStartY = pos.y - bgY; });
document.addEventListener('pointermove', e=>{ if(!bgDragging) return; e.preventDefault(); let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; bgX = pos.x - bgStartX; bgY = pos.y - bgStartY; updateBgTransform(); });
document.addEventListener('pointerup', ()=>{ bgDragging=false; });

function saveChatBg(){
    if(!bgImg.src) return;
    fetch('/update_chat_bg_custom', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ image: bgImg.src, x: bgX, y: bgY, scale: bgScale })
    }).then(r=>r.json()).then(res=>{ if(res.status==='ok'){ alert('Fond de discussion mis à jour !'); closeChatBgModal(); } });
}
</script></body></html>"""

CONTACTS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>Chats</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header" id="mainHeader">
<h2>GenieChat</h2>
<div class="header-actions">
<a href="/archives" style="color:inherit; text-decoration:none;">📦</a>
<a href="/settings"><div class="avatar" style="background-image:url('{{ photo }}')">{{ initial }}</div></a>
</div>
</div>

<div class="nav-tabs">
<a href="/contacts" class="tab-item active">💬 Discussions</a>
<a href="/statuses" class="tab-item">⭕ Statuts</a>
<a href="/channels" class="tab-item">📢 Chaînes</a>
</div>

<div class="header" id="selectionHeader" style="display:none; background:#D93025;">
<button onclick="exitSelection()" style="background:none; border:none; color:white; font-size:20px;">✕</button>
<h2 id="selectedCount">0 sélectionné</h2>
<div class="header-actions">
<button onclick="archiveSelected()" class="btn btn-gray" style="width:auto; padding:6px 12px; margin:0;">Archiver</button>
<button onclick="confirmDelete()" class="btn btn-danger" style="width:auto; padding:6px 12px; margin:0;">Supprimer</button>
</div>
</div>

<div id="page-contacts" class="page active" style="flex:1; display:flex; flex-direction:column;">
<div style="padding:10px 16px; background:#202C33; border-bottom:1px solid #2A3942; display:flex; justify-content:space-between; align-items:center;">
    <b>Mes Contacts & Groupes</b>
    <button class="btn" style="width:auto; padding:8px 12px; margin:0; font-size:14px;" onclick="enableGroupCreationMode()">👥 Créer un Groupe</button>
</div>

<div class="contact-list" id="contact-list">
<!-- Section Groupes -->
{% for g in groups %}
<div class="contact" onclick="location='/group/{{ g.id }}'">
<div class="avatar" style="background-image:url('{{ g.photo }}')">👥</div>
<div class="contact-info"><b>{{ g.name }}</b><br><small style="color:#8696A0;">Groupe: {{ g.members|length }} membres</small></div>
</div>
{% endfor %}

<!-- Section Contacts avec Case à Cocher pour Groupe -->
<form id="groupSelectionForm">
{% for c in contacts %}
<div class="contact" data-code="{{ c }}">
<input type="checkbox" class="group-checkbox" value="{{ c }}" style="display:none; width:20px; height:20px; margin-right:10px;" onchange="checkSelectedGroupContacts()">
<div class="avatar" style="background-image:url('{{ users[c].photo }}')" onclick="handleContactClick('{{ c }}')">{{ users[c].initial }}</div>
<div class="contact-info" onclick="handleContactClick('{{ c }}')"><b>{{ users[c].nom }}</b><br><small style="color:#8696A0;">{{ c }}</small></div>
{% if unread.get(c, 0) > 0 %}<div class="badge">{{ unread[c] }}</div>{% endif %}
</div>{% endfor %}
</form>
</div>

<div id="groupCreateBtnContainer" style="display:none; padding:10px; background:#202C33;">
    <button class="btn" id="btnGoToGroupConfig" onclick="openGroupConfigModal()">Créer Groupe (<span id="selectedGroupCount">0</span>)</button>
</div>

<div class="add-bar"><form method="POST" action="/ajouter" style="display:flex; width:100%; gap:10px;">
<input name="code_ami" placeholder="Entrer CODE de l'ami" class="input" required><button class="btn" style="width:80px; margin:0;">Ajouter</button></form></div>
</div>

<!-- Interface 2 : CONFIGURATION DE GROUPE -->
<div class="popup" id="groupConfigModal">
<div class="popup-box">
<h3>Configuration du Groupe</h3>
<div id="groupProfilePreview" class="avatar-big" style="margin-bottom:10px;">👥</div>
<button class="btn btn-gray" onclick="openGroupProfileCrop()">📷 Ajouter Profil Groupe</button>
<input id="groupConfigName" class="input" placeholder="Nom du groupe..." style="margin-top:15px;">
<div class="popup-buttons">
<button class="btn btn-gray" onclick="closeGroupConfigModal()">Annuler</button>
<button class="btn" onclick="finalizeGroupCreation()">Créer et Entrer dans le groupe</button>
</div>
</div>
</div>

<!-- Modal Recadrage Rond Profil Groupe -->
<div class="crop-modal" id="groupCropModal" style="z-index:150;">
<div class="crop-area"><img id="groupCropImg" class="crop-img"><div class="crop-circle"></div></div>
<div class="crop-buttons">
<button type="button" class="btn btn-gray" onclick="groupZoom(-0.1)">-</button>
<button type="button" class="btn btn-gray" onclick="closeGroupCrop()">Annuler</button>
<button type="button" class="btn btn-gray" onclick="groupZoom(0.1)">+</button>
<button type="button" class="btn" onclick="saveGroupCrop()">Valider</button>
</div>
</div>
<input type="file" id="groupPhotoInput" accept="image/*" style="display:none;" onchange="handleGroupPhotoSelect(event)">

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
let isGroupCreationMode = false;
let groupSelectedContacts = [];
let groupProfileData = "";

socket.emit('join',{code:MY_CODE});

function enableGroupCreationMode(){
    isGroupCreationMode = true;
    document.querySelectorAll('.group-checkbox').forEach(cb => cb.style.display = 'block');
    document.getElementById('groupCreateBtnContainer').style.display = 'block';
}

function checkSelectedGroupContacts(){
    const checkboxes = document.querySelectorAll('.group-checkbox:checked');
    groupSelectedContacts = Array.from(checkboxes).map(cb => cb.value);
    document.getElementById('selectedGroupCount').innerText = groupSelectedContacts.length;
}

function handleContactClick(code){
    if(isGroupCreationMode) return;
    location.href = '/chat/' + code;
}

function openGroupConfigModal(){
    if(groupSelectedContacts.length < 1){ alert("Sélectionnez au moins un contact pour créer un groupe."); return; }
    document.getElementById('groupConfigModal').style.display = 'flex';
}
function closeGroupConfigModal(){ document.getElementById('groupConfigModal').style.display = 'none'; }

function openGroupProfileCrop(){ document.getElementById('groupPhotoInput').click(); }

let gScale=1, gX=0, gY=0, gDragging=false, gStartX=0, gStartY=0;
const gCropImg = document.getElementById('groupCropImg');

function handleGroupPhotoSelect(e){
    const file = e.target.files[0]; if(!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        gCropImg.src = ev.target.result;
        document.getElementById('groupCropModal').style.display = 'flex';
        gScale=0.8; gX=0; gY=0; updateGTransform();
    };
    reader.readAsDataURL(file);
}
function updateGTransform(){ gCropImg.style.transform=`translate(-50%,-50%) translate(${gX}px,${gY}px) scale(${gScale})`; }
function groupZoom(v){ gScale+=v; if(gScale<0.3) gScale=0.3; updateGTransform(); }
function closeGroupCrop(){ document.getElementById('groupCropModal').style.display='none'; }

gCropImg.addEventListener('pointerdown', e=>{ e.preventDefault(); gDragging=true; let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; gStartX = pos.x - gX; gStartY = pos.y - gY; });
document.addEventListener('pointermove', e=>{ if(!gDragging) return; e.preventDefault(); let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; gX = pos.x - gStartX; gY = pos.y - gStartY; updateGTransform(); });
document.addEventListener('pointerup', ()=>{ gDragging=false; });

function saveGroupCrop(){
    const canvas = document.createElement('canvas'); canvas.width=150; canvas.height=150;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(gCropImg, 0, 0, 150, 150);
    groupProfileData = gCropImg.src; 
    document.getElementById('groupProfilePreview').style.backgroundImage = `url(${groupProfileData})`;
    document.getElementById('groupProfilePreview').innerText = '';
    closeGroupCrop();
}

function finalizeGroupCreation(){
    const name = document.getElementById('groupConfigName').value;
    if(!name){ alert("Veuillez entrer un nom de groupe."); return; }
    fetch('/create_group', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ name: name, members: groupSelectedContacts, photo: groupProfileData })
    }).then(r=>r.json()).then(res=>{
        if(res.status==='ok') location.href = '/group/' + res.id;
    });
}

function syncMessages(){
  {% for c in contacts %}
  fetch('/get_msg/{{ c }}').then(r=>r.json()).then(msgs=>{
    localStorage.setItem('chat_{{ my_code }}_{{ c }}', JSON.stringify(msgs));
  });
  {% endfor %}
}
syncMessages();
socket.on('new_message_alert', ()=>{ syncMessages(); });
</script>
</body></html>"""

CHAT_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chat avec {{ ami.nom }}</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><a href="/contacts" style="color:inherit; font-size:24px;">←</a>
<div class="avatar" style="background-image:url('{{ ami.photo }}')">{{ ami.initial }}</div>
<div><b>{{ ami.nom }}</b><br><small style="color:#8696A0;">{{ code_ami }}</small></div></div>
<div class="messages" id="msgBox" style="background-image:url('{{ chat_bg }}')"></div>
<form class="send-box" id="sendForm">
<label class="file-btn" title="Envoyer image ou vidéo">🖼️<input type="file" id="chatFileInput" accept="image/*,video/*" style="display:none;"></label>
<input type="text" id="message" placeholder="Écris un message" class="input">
<button id="micBtn" type="button" class="mic-btn" title="Enregistrer message vocal">🎤</button>
<button id="sendBtn" class="btn" style="border-radius:50%; width:48px; height:48px; padding:0; font-size:20px; display:none; margin:0;">➤</button></form>

<div class="media-viewer" id="mediaViewer">
<img id="viewerImg" style="display:none;"><video id="viewerVideo" controls style="display:none;"></video>
<div class="media-actions">
<a id="downloadBtn" class="btn" download="media_geniechat">💾 Enregistrer</a>
<button class="btn btn-gray" onclick="closeViewer()">Fermer</button>
</div>
</div>

<div class="context-menu" id="contextMenu">
<button onclick="deleteForMe()">Supprimer pour moi</button>
<button onclick="deleteForAll()">Supprimer pour tout le monde</button>
</div>

<script>
const socket=io("{{ central }}");const MY_CODE="{{ my_code }}";const AMI_CODE="{{ code_ami }}";
const STORAGE_KEY = `chat_${MY_CODE}_${AMI_CODE}`;
let mediaRecorder, audioChunks = [], isRecording = false; let selectedMsgId = null;
const micBtn = document.getElementById('micBtn');
const sendBtn = document.getElementById('sendBtn');
const msgInput = document.getElementById('message');

socket.on('connect',()=>socket.emit('join',{code:MY_CODE}));

function openViewer(src, type){
    document.getElementById('mediaViewer').style.display='flex';
    document.getElementById('downloadBtn').href = src;
    if(type=='image'){ document.getElementById('viewerImg').src=src; document.getElementById('viewerImg').style.display='block'; document.getElementById('viewerVideo').style.display='none'; }
    else { document.getElementById('viewerVideo').src=src; document.getElementById('viewerVideo').style.display='block'; document.getElementById('viewerImg').style.display='none'; }
}
function closeViewer(){ document.getElementById('mediaViewer').style.display='none'; const v=document.getElementById('viewerVideo'); v.pause(); v.src=''; }
function showContextMenu(e, msgId){ e.preventDefault(); selectedMsgId=msgId; const menu=document.getElementById('contextMenu'); menu.style.display='block'; menu.style.left=e.pageX+'px'; menu.style.top=e.pageY+'px'; }
document.addEventListener('click', ()=>{ document.getElementById('contextMenu').style.display='none'; })
function deleteForMe(){ fetch('/delete_msg', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:selectedMsgId, type:'pv', ami:AMI_CODE, mode:'me'})}).then(()=>document.getElementById(selectedMsgId).remove()); }
function deleteForAll(){ fetch('/delete_msg', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({id:selectedMsgId, type:'pv', ami:AMI_CODE, mode:'all'})}).then(()=>document.getElementById(selectedMsgId).remove()); }

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
    saveLocal(serverMsgs); render(serverMsgs);
  }).catch(()=>{});
}
load();

function sendData(data){
  let local = loadLocal(); local.push(data); saveLocal(local);
  addMsg(data.from_nom,data.msg,true,data.time,data.status,data.id,data.type); scroll();
  socket.emit('send_message',data);
}

sendBtn.onclick=e=>{e.preventDefault();const msg=msgInput.value;if(!msg)return;
let t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});let id='m'+Date.now();
let data={to:AMI_CODE,from:MY_CODE,from_nom:"{{ my_nom }}",msg:msg,time:t,id:id,type:'text',status:'sent'};
sendData(data);
msgInput.value='';sendBtn.style.display='none';micBtn.style.display='flex';}

msgInput.oninput=()=>{sendBtn.style.display=msgInput.value?'block':'none'; micBtn.style.display=msgInput.value?'none':'flex';}

document.getElementById('chatFileInput').onchange = e => {
    const file=e.target.files[0]; if(!file) return;
    const reader=new FileReader();
    reader.onload=ev=>{
        let t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
        sendData({to:AMI_CODE,from:MY_CODE,from_nom:"{{ my_nom }}",msg:ev.target.result,time:t,id:'m'+Date.now(),type:'file'});
        e.target.value = '';
    }
    reader.readAsDataURL(file);
}

micBtn.onclick = async () => {
  if (!isRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream);
      audioChunks = [];
      mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        const reader = new FileReader();
        reader.onloadend = () => {
          let t = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
          let id = 'm' + Date.now();
          let data = { to: AMI_CODE, from: MY_CODE, from_nom: "{{ my_nom }}", msg: reader.result, time: t, id: id, type: 'audio', status: 'sent' };
          sendData(data);
        };
        reader.readAsDataURL(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };
      mediaRecorder.start();
      isRecording = true;
      micBtn.classList.add('recording');
    } catch (err) { alert("Impossible d'accéder au microphone."); }
  } else {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') { mediaRecorder.stop(); }
    isRecording = false; micBtn.classList.remove('recording');
  }
};

function addMsg(from,msg,me,time,status,id,type='text'){
  let d=document.createElement('div');d.id=id;d.className='msg '+(me?'me':'you'); d.oncontextmenu=(e)=>showContextMenu(e,id);
  let check = me? (status=='read'?'<span class="check blue">✓</span>':'<span class="check gray">✓</span>') : '';
  let content = type=='audio'? `<audio controls class="audio-player" src="${msg}"></audio>` : type=='file'? (msg.startsWith('data:image')? `<img src="${msg}" class="chat-img" onclick="openViewer('${msg}','image')">` : msg.startsWith('data:video')? `<video src="${msg}" class="chat-video" onclick="openViewer('${msg}','video')"></video>` : `<a href="${msg}" target="_blank" style="color:inherit;">📎 Fichier</a>`) : msg;
  d.innerHTML=`${content}<div class="time">${time} ${check}</div>`;document.getElementById('msgBox').append(d);
}
function scroll(){let box=document.getElementById('msgBox');box.scrollTop=box.scrollHeight;}
socket.on('receive_message',d=>{
    if(d.from==AMI_CODE){
      let local = loadLocal(); local.push(d); saveLocal(local);
      addMsg(d.from_nom,d.msg,false,d.time,'read',d.id,d.type);scroll();
    }
});
</script></body></html>"""

GROUP_CHAT_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Groupe: {{ group.name }}</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header">
<a href="/contacts" style="color:inherit; font-size:24px;">←</a>
<div class="avatar" style="background-image:url('{{ group.photo }}')">👥</div>
<div><b>{{ group.name }}</b><br><small style="color:#8696A0;">{{ group.members|length }} membres</small></div>
<div class="header-actions">
    <button class="btn btn-gray" style="width:auto; padding:6px 10px; margin:0; font-size:12px;" onclick="openAddMemberModal()">➕ Ajouter contact</button>
    <button class="btn btn-gray" style="width:auto; padding:6px 10px; margin:0; font-size:12px;" onclick="openMembersModal()">👥 {{ group.members|length }} Admis</button>
</div>
</div>

<div class="messages" id="msgBox" style="background-image:url('{{ group_bg }}')"></div>
<form class="send-box" id="sendForm">
<label class="file-btn" title="Envoyer image ou vidéo">🖼️<input type="file" id="groupFileInput" accept="image/*,video/*" style="display:none;"></label>
<input type="text" id="message" placeholder="Message du groupe..." class="input">
<button id="micBtn" type="button" class="mic-btn" title="Enregistrer message vocal">🎤</button>
<button id="sendBtn" class="btn" style="border-radius:50%; width:48px; height:48px; padding:0; font-size:20px; display:none; margin:0;">➤</button></form>

<!-- Modal Ajouter Contact au Groupe -->
<div class="popup" id="addMemberModal">
<div class="popup-box">
<h3>Ajouter des Contacts</h3>
<div style="max-height:200px; overflow-y:auto; text-align:left; margin:10px 0;">
{% for c in all_contacts %}
{% if c not in group.members %}
<div style="padding:8px; border-bottom:1px solid #2A3942; display:flex; align-items:center; gap:10px;">
    <input type="checkbox" class="new-member-cb" value="{{ c }}">
    <span><b>{{ users[c].nom }}</b> ({{ c }})</span>
</div>
{% endif %}
{% endfor %}
</div>
<div class="popup-buttons">
<button class="btn btn-gray" onclick="closeAddMemberModal()">Annuler</button>
<button class="btn" onclick="addSelectedMembers()">Ajouter</button>
</div>
</div>
</div>

<!-- Modal Membres Admis & Fonction Cachée Discuter en Privé -->
<div class="popup" id="membersModal">
<div class="popup-box">
<h3>Membres Admis au Groupe</h3>
<p style="font-size:11px; color:#8696A0;">Cliquez sur un membre pour discuter en privé</p>
<div style="max-height:250px; overflow-y:auto; text-align:left; margin:15px 0;">
{% for m in group.members %}
<div class="contact" onclick="promptPrivateChat('{{ m }}', '{{ users[m].nom if m in users else m }}')">
    <div class="avatar" style="background-image:url('{{ users[m].photo if m in users else '' }}')">👤</div>
    <div class="contact-info"><b>{{ users[m].nom if m in users else m }}</b><br><small style="color:#8696A0;">{{ m }}</small></div>
</div>
{% endfor %}
</div>
<button class="btn btn-gray" onclick="closeMembersModal()">Fermer</button>
</div>
</div>

<!-- Popup Fonction Cachée Discussion Privée -->
<div class="popup" id="privateChatPromptModal">
<div class="popup-box">
<h3>Discussion Privée</h3>
<p id="privatePromptText">Discuter avec cette personne en privé ?</p>
<div class="popup-buttons">
<button class="btn btn-gray" onclick="closePrivatePrompt()">Annuler</button>
<button class="btn" onclick="confirmPrivateChat()">OK</button>
</div>
</div>
</div>

<script>
const socket=io("{{ central }}");const MY_CODE="{{ my_code }}";const GROUP_ID="{{ group.id }}";
let selectedPrivateCode = "";

socket.on('connect',()=>socket.emit('join',{code:GROUP_ID}));

function openAddMemberModal(){ document.getElementById('addMemberModal').style.display='flex'; }
function closeAddMemberModal(){ document.getElementById('addMemberModal').style.display='none'; }
function openMembersModal(){ document.getElementById('membersModal').style.display='flex'; }
function closeMembersModal(){ document.getElementById('membersModal').style.display='none'; }

function addSelectedMembers(){
    const cbs = document.querySelectorAll('.new-member-cb:checked');
    const newMembers = Array.from(cbs).map(c => c.value);
    if(newMembers.length < 1) return;
    fetch('/add_group_members', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ group_id: GROUP_ID, members: newMembers })
    }).then(r=>r.json()).then(res=>{ if(res.status==='ok') location.reload(); });
}

/* Fonction Cachée : Discuter en Privé depuis le Groupe */
function promptPrivateChat(code, nom){
    if(code === MY_CODE) return;
    selectedPrivateCode = code;
    document.getElementById('privatePromptText').innerText = `Discuter avec ${nom} en privé ?`;
    document.getElementById('privateChatPromptModal').style.display = 'flex';
}
function closePrivatePrompt(){ document.getElementById('privateChatPromptModal').style.display = 'none'; }
function confirmPrivateChat(){
    fetch('/ajouter_direct', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ code_ami: selectedPrivateCode })
    }).then(r=>r.json()).then(res=>{
        if(res.status==='ok'){ location.href = '/chat/' + selectedPrivateCode; }
    });
}

function loadGroup(){
  fetch('/get_group_msgs/'+GROUP_ID).then(r=>r.json()).then(msgs=>{
    document.getElementById('msgBox').innerHTML='';
    msgs.forEach(m=>addMsg(m.from_nom,m.msg,m.from==MY_CODE,m.time,m.id,m.type));
    scroll();
  });
}
loadGroup();

function sendData(data){
  addMsg(data.from_nom,data.msg,true,data.time,data.id,data.type); scroll();
  socket.emit('send_group_message',data);
}

const sendBtn = document.getElementById('sendBtn');
const micBtn = document.getElementById('micBtn');
const msgInput = document.getElementById('message');

sendBtn.onclick=e=>{e.preventDefault();const msg=msgInput.value;if(!msg)return;
let t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});let id='m'+Date.now();
let data={group:GROUP_ID,from:MY_CODE,from_nom:"{{ my_nom }}",msg:msg,time:t,id:id,type:'text'};
sendData(data); msgInput.value='';sendBtn.style.display='none';micBtn.style.display='flex';}

msgInput.oninput=()=>{sendBtn.style.display=msgInput.value?'block':'none'; micBtn.style.display=msgInput.value?'none':'flex';}

function addMsg(from,msg,me,time,id,type='text'){
  let d=document.createElement('div');d.id=id;d.className='msg '+(me?'me':'you');
  let content = type=='audio'? `<audio controls class="audio-player" src="${msg}"></audio>` : type=='file'? (msg.startsWith('data:image')? `<img src="${msg}" class="chat-img">` : msg.startsWith('data:video')? `<video src="${msg}" class="chat-video"></video>` : `<a href="${msg}" target="_blank">📎 Fichier</a>`) : msg;
  d.innerHTML=`<b>${from}</b><br>${content}<div class="time">${time}</div>`;document.getElementById('msgBox').append(d);
}
function scroll(){let box=document.getElementById('msgBox');box.scrollTop=box.scrollHeight;}
socket.on('receive_group_message',d=>{ if(d.group==GROUP_ID){ addMsg(d.from_nom,d.msg,false,d.time,d.id,d.type);scroll(); } });
</script></body></html>"""

STATUSES_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Statuts</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header">
<a href="/contacts" style="color:inherit; font-size:24px;">←</a>
<h2>Statut</h2>
<a href="/status_comments_page" style="color:inherit; font-size:20px; text-decoration:none;">💬</a>
</div>

<div class="nav-tabs">
<a href="/contacts" class="tab-item">💬 Discussions</a>
<a href="/statuses" class="tab-item active">⭕ Statuts</a>
<a href="/channels" class="tab-item">📢 Chaînes</a>
</div>

<div style="padding:15px;">
<button onclick="document.getElementById('statusFile').click()" class="btn">➕ Ajouter statut</button>
<input type="file" id="statusFile" accept="image/*,video/*" style="display:none;" onchange="handleStatusSelect(event)">
</div>

<div class="contact-list" id="status-list">
<h3 style="padding:10px 16px; color:#8696A0; font-size:14px;">Mises à jour récentes</h3>
{% for code, data in contact_statuses.items() %}
<div class="contact" onclick="viewStatus('{{ code }}')">
<div class="avatar" style="background-image:url('{{ data.user.photo }}'); border:2px solid #00A884;">{{ data.user.initial }}</div>
<div class="contact-info"><b>{{ data.user.nom }}</b><br><small style="color:#8696A0;">{{ data.list|length }} statut(s)</small></div>
</div>
{% else %}
<p style="text-align:center; padding:20px; color:#8696A0;">Aucun statut disponible</p>
{% endfor %}
</div>

<!-- Modal d'édition Cadrage Plein Écran + Éditeur Musique -->
<div class="crop-modal" id="statusEditorModal" style="z-index:200;">
<div style="position:absolute; top:15px; left:15px; right:15px; display:flex; justify-content:space-between; z-index:205;">
<button class="btn btn-gray" style="width:auto; margin:0;" onclick="closeStatusEditor()">✕</button>
<button class="btn" style="width:auto; margin:0;" id="btnPublishStatus" onclick="publishStatus()">Publier</button>
</div>

<div class="crop-area" id="editorCanvasArea">
<img id="statusCropImg" style="position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); touch-action:none; cursor:grab;">
<video id="editorVideo" controls style="max-width:100%; max-height:70vh; display:none;"></video>
<div class="crop-square" id="cropSquareGuide"></div>
</div>

<div style="position:absolute; bottom:20px; width:90%; display:flex; flex-direction:column; gap:8px; z-index:205;">
<div style="display:flex; gap:10px; justify-content:center;">
    <button class="btn btn-gray" style="width:auto;" onclick="openMusicPicker()">🎵 Éditeur Musique</button>
</div>

<!-- Éditeur de musique avec crochets glissants -->
<div id="musicEditorContainer" class="audio-range-box" style="display:none;">
    <small style="color:#00A884; font-weight:bold;" id="musicTitle">Musique Sélectionnée</small>
    <div style="font-family:monospace; font-size:16px; margin:8px 0; color:white;" id="crochetDiagram">
        -x--[----•______]___x___
    </div>
    <div style="display:flex; gap:10px; align-items:center;">
        <span style="font-size:11px;">Début:</span>
        <input type="range" id="startCrochet" min="0" max="100" value="20" oninput="updateMusicCrop()">
        <span style="font-size:11px;">Fin:</span>
        <input type="range" id="endCrochet" min="0" max="100" value="80" oninput="updateMusicCrop()">
    </div>
</div>

<input id="textOverlayInput" class="input" placeholder="Écrire une légende...">
</div>
</div>

<input type="file" id="musicFileInput" accept="audio/*" style="display:none;" onchange="handleMusicSelect(event)">

<!-- Modal Visionnement Statuts -->
<div class="media-viewer" id="statusViewerModal" style="z-index:300;">
<div style="position:absolute; top:15px; left:15px; right:15px; display:flex; justify-content:space-between; color:white; align-items:center; z-index:305;">
<b id="viewerUserNom">Nom</b>
<div>
<a id="saveStatusBtn" class="btn btn-gray" style="display:inline-block; width:auto; padding:8px 12px; margin:0;" download>💾 Enregistrer</a>
<button class="btn btn-gray" style="display:inline-block; width:auto; padding:8px 12px; margin:0;" onclick="closeStatusViewer()">✕</button>
</div>
</div>
<div id="statusMediaContainer" style="width:100%; height:70vh; display:flex; flex-direction:column; justify-content:center; align-items:center;" onclick="nextStatus()"></div>
</div>

<script>
let currentMediaData = null;
let musicAudioData = null;
let stScale=1, stX=0, stY=0, stDragging=false, stStartX=0, stStartY=0;
const stImg = document.getElementById('statusCropImg');

function handleStatusSelect(e){
    const file = e.target.files[0]; if(!file) return;
    const reader = new FileReader();
    reader.onload = function(ev){
        currentMediaData = { src: ev.target.result, type: file.type.startsWith('video')?'video':'image' };
        openStatusEditor();
    };
    reader.readAsDataURL(file);
}

function openStatusEditor(){
    document.getElementById('statusEditorModal').style.display = 'flex';
    if(currentMediaData.type === 'image'){
        stImg.src = currentMediaData.src; stImg.style.display = 'block';
        document.getElementById('editorVideo').style.display = 'none';
        document.getElementById('cropSquareGuide').style.display = 'block';
        stScale=1; stX=0; stY=0; updateStTransform();
    } else {
        const vid = document.getElementById('editorVideo');
        vid.src = currentMediaData.src; vid.style.display = 'block';
        stImg.style.display = 'none';
        document.getElementById('cropSquareGuide').style.display = 'none';
    }
}
function closeStatusEditor(){ document.getElementById('statusEditorModal').style.display = 'none'; }

function updateStTransform(){ stImg.style.transform = `translate(-50%,-50%) translate(${stX}px,${stY}px) scale(${stScale})`; }
stImg.addEventListener('pointerdown', e=>{ e.preventDefault(); stDragging=true; let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; stStartX = pos.x - stX; stStartY = pos.y - stY; });
document.addEventListener('pointermove', e=>{ if(!stDragging) return; e.preventDefault(); let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; stX = pos.x - stStartX; stY = pos.y - stStartY; updateStTransform(); });
document.addEventListener('pointerup', ()=>{ stDragging=false; });

function openMusicPicker(){ document.getElementById('musicFileInput').click(); }
function handleMusicSelect(e){
    const file = e.target.files[0]; if(!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        musicAudioData = ev.target.result;
        document.getElementById('musicTitle').innerText = "🎵 " + file.name;
        document.getElementById('musicEditorContainer').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

function updateMusicCrop(){
    let s = document.getElementById('startCrochet').value;
    let e = document.getElementById('endCrochet').value;
    document.getElementById('crochetDiagram').innerText = `-x--[${s}%---•___${e}%]___x___`;
}

function publishStatus(){
    const text = document.getElementById('textOverlayInput').value;
    fetch('/publish_status', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({
            media: currentMediaData.src,
            type: currentMediaData.type,
            text_overlay: text,
            music: musicAudioData
        })
    }).then(r=>r.json()).then(res=>{
        if(res.status==='ok'){
            closeStatusEditor();
            location.reload(); // Retour automatique à l'onglet statut
        }
    });
}

const allStatuses = {{ contact_statuses|tojson }};
let currentContactStatuses = [], currentStatusIndex = 0;

function viewStatus(code){
    if(!allStatuses[code]) return;
    currentContactStatuses = allStatuses[code].list; currentStatusIndex = 0;
    document.getElementById('viewerUserNom').innerText = allStatuses[code].user.nom;
    document.getElementById('statusViewerModal').style.display = 'flex';
    renderCurrentStatus();
}

function renderCurrentStatus(){
    if(currentStatusIndex >= currentContactStatuses.length){ closeStatusViewer(); return; }
    const st = currentContactStatuses[currentStatusIndex];
    const container = document.getElementById('statusMediaContainer');
    document.getElementById('saveStatusBtn').href = st.media;
    
    let musicHtml = st.music ? `<audio src="${st.music}" autoplay loop style="margin-top:10px;"></audio>` : '';
    if(st.type === 'image'){
        container.innerHTML = `<img src="${st.media}" style="max-width:100%; max-height:60vh;"><div style="color:white; font-size:18px; margin-top:10px;">${st.text_overlay || ''}</div>${musicHtml}`;
    } else {
        container.innerHTML = `<video src="${st.media}" autoplay controls style="max-width:100%; max-height:60vh;"></video><div style="color:white; font-size:18px; margin-top:10px;">${st.text_overlay || ''}</div>`;
    }
}

function nextStatus(){ currentStatusIndex++; renderCurrentStatus(); }
function closeStatusViewer(){ document.getElementById('statusViewerModal').style.display = 'none'; }
</script>
</body></html>"""

CHANNELS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chaînes</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><a href="/contacts" style="color:inherit; font-size:24px;">←</a><h2>Chaînes</h2><div></div></div>

<div class="nav-tabs">
<a href="/contacts" class="tab-item">💬 Discussions</a>
<a href="/statuses" class="tab-item">⭕ Statuts</a>
<a href="/channels" class="tab-item active">📢 Chaînes</a>
</div>

<div style="padding:15px;">
<button onclick="openConfigChannel()" class="btn">📢 Créer une chaîne</button>
<input id="searchChannel" class="input" placeholder="Rechercher une chaîne..." oninput="searchChannels(this.value)">
</div>

<div class="contact-list" id="channel-list">
{% for ch in channels %}
<div class="contact" onclick="location='/channel/{{ ch.id }}'">
<div class="avatar" style="background-image:url('{{ ch.photo }}')">📢</div>
<div class="contact-info">
<b>{{ ch.name }}</b><br>
<small style="color:#8696A0;">{{ ch.followers|length }} Followers</small>
</div>
</div>
{% else %}
<p style="text-align:center; padding:20px; color:#8696A0;">Aucune chaîne disponible</p>
{% endfor %}
</div>

<!-- Configuration Création Chaîne avec Recadrage Simulation -->
<div class="popup" id="configChannelPopup">
<div class="popup-box">
<h3>Configurer la Chaîne</h3>
<div id="channelPreview" class="avatar-big" style="margin-bottom:10px;">📢</div>
<button class="btn btn-gray" onclick="document.getElementById('channelPhotoInput').click()">📷 Photo Chaîne</button>
<input id="channelNameInput" class="input" placeholder="Nom de la chaîne..." style="margin-top:15px;">
<div class="popup-buttons">
<button class="btn btn-gray" onclick="closeConfigChannel()">Annuler</button>
<button class="btn" onclick="enterChannelCreation()">Créer Chaîne</button>
</div>
</div>
</div>

<div class="crop-modal" id="channelCropModal" style="z-index:160;">
<div class="crop-area"><img id="channelCropImg" class="crop-img"><div class="crop-circle"></div></div>
<div class="crop-buttons">
<button type="button" class="btn btn-gray" onclick="chZoom(-0.1)">-</button>
<button type="button" class="btn btn-gray" onclick="closeChCrop()">Annuler</button>
<button type="button" class="btn btn-gray" onclick="chZoom(0.1)">+</button>
<button type="button" class="btn" onclick="saveChCrop()">Valider</button>
</div>
</div>
<input type="file" id="channelPhotoInput" accept="image/*" style="display:none;" onchange="handleChPhotoSelect(event)">

<script>
let channelPhotoData = "";
function openConfigChannel(){ document.getElementById('configChannelPopup').style.display = 'flex'; }
function closeConfigChannel(){ document.getElementById('configChannelPopup').style.display = 'none'; }

let chScale=1, chX=0, chY=0, chDragging=false, chStartX=0, chStartY=0;
const chCropImg = document.getElementById('channelCropImg');

function handleChPhotoSelect(e){
    const file = e.target.files[0]; if(!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        chCropImg.src = ev.target.result;
        document.getElementById('channelCropModal').style.display = 'flex';
        chScale=0.8; chX=0; chY=0; updateChTransform();
    };
    reader.readAsDataURL(file);
}
function updateChTransform(){ chCropImg.style.transform=`translate(-50%,-50%) translate(${chX}px,${chY}px) scale(${chScale})`; }
function chZoom(v){ chScale+=v; if(chScale<0.3) chScale=0.3; updateChTransform(); }
function closeChCrop(){ document.getElementById('channelCropModal').style.display='none'; }

chCropImg.addEventListener('pointerdown', e=>{ e.preventDefault(); chDragging=true; let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; chStartX = pos.x - chX; chStartY = pos.y - chY; });
document.addEventListener('pointermove', e=>{ if(!chDragging) return; e.preventDefault(); let pos = {x:e.touches?e.touches[0].clientX:e.clientX, y:e.touches?e.touches[0].clientY:e.clientY}; chX = pos.x - chStartX; chY = pos.y - chStartY; updateChTransform(); });
document.addEventListener('pointerup', ()=>{ chDragging=false; });

function saveChCrop(){
    channelPhotoData = chCropImg.src;
    document.getElementById('channelPreview').style.backgroundImage = `url(${channelPhotoData})`;
    document.getElementById('channelPreview').innerText = '';
    closeChCrop();
}

function enterChannelCreation(){
    const name = document.getElementById('channelNameInput').value;
    if(!name){ alert("Veuillez entrer un nom"); return; }
    fetch('/create_channel', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ name: name, photo: channelPhotoData })
    }).then(r=>r.json()).then(res=>{
        if(res.status==='ok') location.href = '/channel/' + res.id;
    });
}
</script>
</body></html>"""

CHANNEL_VIEW_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ channel.name }}</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header">
<a href="/channels" style="color:inherit; font-size:24px;">←</a>
<div class="avatar" style="background-image:url('{{ channel.photo }}')">📢</div>
<div>
<b>{{ channel.name }}</b><br>
<small style="color:#8696A0;">{{ channel.followers|length }} Followers</small>
</div>
{% if is_owner %}
<span class="badge" style="border-radius:5px;">Créateur</span>
{% else %}
<button class="btn" style="width:auto; padding:6px 12px; margin:0;" onclick="toggleFollow()">{{ 'Suivi' if is_following else 'Follow' }}</button>
{% endif %}
</div>

<div class="messages" id="msgBox">
{% for m in msgs %}
<div class="msg you" style="align-self:center; max-width:90%;">
<b>{{ m.from_nom }}</b><br>
{% if m.type == 'file' %}
{% if m.msg.startswith('data:image') %}
<img src="{{ m.msg }}" class="chat-img">
{% elif m.msg.startswith('data:video') %}
<video src="{{ m.msg }}" controls class="chat-video"></video>
{% else %}
<a href="{{ m.msg }}" target="_blank" style="color:inherit;">📄 Document</a>
{% endif %}
{% else %}
{{ m.msg }}
{% endif %}
<div class="time">{{ m.time }}</div>
</div>
{% endfor %}
</div>

{% if is_owner %}
<form class="send-box" id="sendForm">
<label class="file-btn" title="Publier image, vidéo ou document">📎<input type="file" id="channelFileInput" accept="image/*,video/*,application/pdf" style="display:none;"></label>
<input type="text" id="message" placeholder="Publier dans la chaîne..." class="input">
<button id="sendBtn" class="btn" style="border-radius:50%; width:48px; height:48px; padding:0; font-size:20px; margin:0;">➤</button>
</form>
{% endif %}

<script>
const socket = io("{{ central }}");
const CHANNEL_ID = "{{ channel.id }}";
const IS_OWNER = {{ 'true' if is_owner else 'false' }};
const MY_CODE = "{{ my_code }}";

socket.on('connect', ()=> socket.emit('join', {code: CHANNEL_ID}));

if(IS_OWNER){
    document.getElementById('sendForm').onsubmit = e => {
        e.preventDefault();
        const msg = document.getElementById('message').value;
        if(!msg) return;
        let t = new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
        const data = { channel: CHANNEL_ID, from: MY_CODE, from_nom: "{{ my_nom }}", msg: msg, time: t, type: 'text' };
        fetch('/publish_channel_msg', {
            method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify(data)
        }).then(()=> location.reload());
    };

    document.getElementById('channelFileInput').onchange = e => {
        const file = e.target.files[0]; if(!file) return;
        const reader = new FileReader();
        reader.onload = ev => {
            let t = new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
            const data = { channel: CHANNEL_ID, from: MY_CODE, from_nom: "{{ my_nom }}", msg: ev.target.result, time: t, type: 'file' };
            fetch('/publish_channel_msg', {
                method:'POST', headers:{'Content-Type':'application/json'},
                body: JSON.stringify(data)
            }).then(()=> location.reload());
        };
        reader.readAsDataURL(file);
    };
}

function toggleFollow(){
    fetch('/toggle_follow_channel', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ channel_id: CHANNEL_ID })
    }).then(()=> location.reload());
}
</script>
</body></html>"""

STATUS_COMMENTS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Commentaires des Statuts</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style></head><body>
<div class="header"><a href="/statuses" style="color:inherit; font-size:24px;">←</a><h2>Commentaires Statuts</h2><div></div></div>
<div class="contact-list">
{% for c in comments %}
<div class="contact">
<div class="avatar">💬</div>
<div class="contact-info">
<b>{{ c.from_nom }}</b><br><span>{{ c.comment }}</span><br><small style="color:#8696A0;">{{ c.time }}</small>
</div>
</div>
{% else %}
<p style="text-align:center; padding:20px; color:#8696A0;">Aucun commentaire reçu.</p>
{% endfor %}
</div>
</body></html>"""

EXPLORE_STATUSES_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Explorer Statuts</title><style>{{ CSS_BASE }}{{ THEME_CSS }}</style></head><body style="background:#000; overflow:hidden;">
<div style="position:fixed; top:15px; left:15px; z-index:100;">
<a href="/statuses" class="btn btn-gray" style="width:auto; padding:8px 15px; text-decoration:none;">← Retour</a>
</div>
<div class="tiktok-container">
{% for st in explore_statuses %}
<div class="tiktok-slide">
{% if st.type == 'image' %}
<img src="{{ st.media }}" class="tiktok-media">
{% else %}
<video src="{{ st.media }}" controls autoplay loop class="tiktok-media"></video>
{% endif %}
<div class="tiktok-overlay">
<b>@{{ st.user_nom }}</b>
<p>{{ st.text_overlay }}</p>
</div>
</div>
{% else %}
<div class="tiktok-slide"><h3 style="color:white;">Aucun statut à explorer</h3></div>
{% endfor %}
</div>
</body></html>"""

def get_user():
    code = session.get('code')
    db = load_db()
    return code, db["USERS"].get(code), db

def login():
    code, user, db = get_user()
    theme = get_user_settings(code, db)["theme"] if code else "noir"
    if user: return render_template_string(LOGIN_HTML, CSS_BASE=CSS_BASE, THEME_CSS=get_theme_css(theme), code=code, nom=user['nom'])
    return render_template_string(LOGIN_HTML, CSS_BASE=CSS_BASE, THEME_CSS=get_theme_css(theme), code=None, nom=None)

@app.route('/')
def index():
    return login()

@app.route('/register', methods=['GET','POST'])
def register():
    code, _, db = get_user()
    theme = get_user_settings(code, db)["theme"] if code else "noir"
    if request.method == 'GET': return render_template_string(REGISTER_HTML, CSS_BASE=CSS_BASE, THEME_CSS=get_theme_css(theme))
    db = load_db()
    nom = request.form['nom']; code = gen_code_port(); photo = ""
    if request.form.get('original_img'):
        try:
            x=float(request.form.get('crop_x','0')); y=float(request.form.get('crop_y','0')); s=float(request.form.get('crop_scale','1'))
            img = Image.open(BytesIO(base64.b64decode(request.form['original_img'].split(',')[1])))
            size=200; cx=img.width/2; cy=img.height/2; left=cx-(size/2)/s-x/s; top=cy-(size/2)/s-y/s; right=cx+(size/2)/s-x/s; bottom=cy+(size/2)/s-y/s
            img = img.crop((left,top,right,bottom)).resize((150,150), Image.LANCZOS)
            buf = BytesIO(); img.save(buf, format="PNG")
            photo = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        except: pass
    db["USERS"][code] = {"nom": nom, "photo": photo, "contacts": []}
    db["SETTINGS"][code] = {"theme": "noir", "chat_bg": "", "group_bg": {}}
    if code not in db["ARCHIVED"]: db["ARCHIVED"][code] = []
    save_db(db); session['code'] = code; return redirect('/')

@app.route('/login', methods=['POST'])
def do_login():
    db = load_db(); code = request.form['code'].upper()
    if code in db["USERS"]: session['code'] = code; return redirect('/')
    return "Code introuvable", 404

@app.route('/settings')
def settings():
    code, user, db = get_user()
    if not code: return redirect('/')
    settings = get_user_settings(code, db)
    initial = '' if user['photo'] else avatar_letter(user['nom'])
    return render_template_string(SETTINGS_HTML, CSS_BASE=CSS_BASE, THEME_CSS=get_theme_css(settings["theme"]), nom=user['nom'], photo=user['photo'], code=code, initial=initial, theme=settings["theme"])

@app.route('/update_profile', methods=['POST'])
def update_profile():
    code, user, db = get_user()
    if not code: return redirect('/')
    user['nom'] = request.form['nom']
    if request.form.get('original_img') and request.form.get('original_img')!= "":
        try:
            x=float(request.form.get('crop_x','0')); y=float(request.form.get('crop_y','0')); s=float(request.form.get('crop_scale','1'))
            img = Image.open(BytesIO(base64.b64decode(request.form['original_img'].split(',')[1])))
            size=200; cx=img.width/2; cy=img.height/2; left=cx-(size/2)/s-x/s; top=cy-(size/2)/s-y/s; right=cx+(size/2)/s-x/s; bottom=cy+(size/2)/s-y/s
            img = img.crop((left,top,right,bottom)).resize((150,150), Image.LANCZOS)
            buf = BytesIO(); img.save(buf, format="PNG")
            user['photo'] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception as e: print("Crop error:", e)
    db["USERS"][code] = user; save_db(db); return redirect('/settings')

@app.route('/update_theme', methods=['POST'])
def update_theme():
    code, user, db = get_user()
    if not code: return redirect('/')
    theme = request.form['theme']
    db["SETTINGS"][code]["theme"] = theme
    save_db(db); return redirect('/settings')

@app.route('/update_chat_bg_custom', methods=['POST'])
def update_chat_bg_custom():
    code, user, db = get_user()
    if not code: return jsonify({"status":"error"}), 403
    data = request.json
    db["SETTINGS"][code]["chat_bg"] = data['image']
    save_db(db)
    return jsonify({"status":"ok"})

@app.route('/logout')
def logout(): session.pop('code', None); return redirect('/')

@app.route('/contacts')
def contacts():
    code, user, db = get_user()
    if not code: return redirect('/')
    settings = get_user_settings(code, db)
    user_unread = db["UNREAD"].get(code, {})
    archived = db["ARCHIVED"].get(code, [])
    active_contacts = [c for c in user['contacts'] if c not in archived]
    user_groups = [g for g in db["GROUPS"].values() if code in g['members']]

    users_data = {}
    for c, u in db["USERS"].items():
        initial = '' if u['photo'] else avatar_letter(u['nom'])
        users_data[c] = {"nom": u['nom'], "photo": u['photo'], "initial": initial}

    my_initial = '' if user['photo'] else avatar_letter(user['nom'])
    return render_template_string(CONTACTS_HTML, CSS_BASE=CSS_BASE, THEME_CSS=get_theme_css(settings["theme"]), nom=user['nom'], photo=user['photo'], initial=my_initial, users=users_data, contacts=active_contacts, groups=user_groups, unread=user_unread, my_code=code, central=CENTRAL_SERVER)

@app.route('/ajouter', methods=['GET', 'POST'])
def ajouter():
    code, user, db = get_user()
    if not code: return redirect('/')
    if request.method == 'GET': return redirect('/contacts')
    code_ami = request.form['code_ami'].upper().strip()
    if code_ami in db["USERS"]:
        if code_ami not in user['contacts']: user['contacts'].append(code_ami)
        if code not in db["USERS"][code_ami]['contacts']: db["USERS"][code_ami]['contacts'].append(code)
        db["USERS"][code] = user; save_db(db); return redirect(f'/chat/{code_ami}')
    else: return "Code introuvable", 404

@app.route('/ajouter_direct', methods=['POST'])
def ajouter_direct():
    code, user, db = get_user()
    if not code: return jsonify({"status":"error"}), 403
    data = request.json
    code_ami = data['code_ami']
    if code_ami in db["USERS"]:
        if code_ami not in user['contacts']: user['contacts'].append(code_ami)
        if code not in db["USERS"][code_ami]['contacts']: db["USERS"][code_ami]['contacts'].append(code)
        db["USERS"][code] = user; save_db(db)
        return jsonify({"status":"ok"})
    return jsonify({"status":"error"}), 404

@app.route('/chat/<code_ami>')
def chat(code_ami):
    code, user, db = get_user()
    if not code: return redirect('/')
    settings = get_user_settings(code, db)
    if code in db["UNREAD"] and code_ami in db["UNREAD"][code]:
        db["UNREAD"][code][code_ami] = 0; save_db(db)
    
    ami = db["USERS"].get(code_ami)
    if not ami: return "Utilisateur non trouvé", 404
    
    ami_data = {
        "nom": ami['nom'],
        "photo": ami['photo'],
        "initial": avatar_letter(ami['nom']) if not ami['photo'] else ''
    }
    chat_bg = settings.get("chat_bg", "")
    return render_template_string(
        CHAT_HTML,
        CSS_BASE=CSS_BASE,
        THEME_CSS=get_theme_css(settings["theme"]),
        ami=ami_data,
        code_ami=code_ami,
        my_code=code,
        my_nom=user['nom'],
        chat_bg=chat_bg,
        central=CENTRAL_SERVER
    )

@app.route('/get_msg/<code_ami>')
def get_msg(code_ami):
    code, user, db = get_user()
    if not code: return jsonify([]), 403
    pair_key = "_".join(sorted([code, code_ami]))
    msgs = db["MESSAGES"].get(pair_key, [])
    return jsonify(msgs)

@app.route('/delete_msg', methods=['POST'])
def delete_msg():
    code, user, db = get_user()
    if not code: return jsonify({"status": "error"}), 403
    data = request.json
    msg_id = data.get('id')
    mode = data.get('mode')
    
    if data.get('type') == 'pv':
        ami = data.get('ami')
        pair_key = "_".join(sorted([code, ami]))
        if pair_key in db["MESSAGES"]:
            if mode == 'all':
                db["MESSAGES"][pair_key] = [m for m in db["MESSAGES"][pair_key] if m.get('id') != msg_id]
            save_db(db)
    return jsonify({"status": "ok"})

@app.route('/create_group', methods=['POST'])
def create_group():
    code, user, db = get_user()
    if not code: return jsonify({"status": "error"}), 403
    data = request.json
    group_id = gen_code_port()
    members = list(set(data.get('members', []) + [code]))
    
    db["GROUPS"][group_id] = {
        "id": group_id,
        "name": data.get('name'),
        "photo": data.get('photo', ''),
        "creator": code,
        "members": members
    }
    db["GROUP_MSGS"][group_id] = []
    save_db(db)
    return jsonify({"status": "ok", "id": group_id})

@app.route('/group/<group_id>')
def group_chat(group_id):
    code, user, db = get_user()
    if not code: return redirect('/')
    group = db["GROUPS"].get(group_id)
    if not group or code not in group['members']: return "Groupe introuvable ou accès refusé", 404
    
    settings = get_user_settings(code, db)
    group_bg = settings.get("group_bg", {}).get(group_id, "")
    
    users_data = {}
    for m in group['members']:
        u = db["USERS"].get(m, {})
        users_data[m] = {"nom": u.get('nom', m), "photo": u.get('photo', '')}

    all_contacts = user.get('contacts', [])
    return render_template_string(
        GROUP_CHAT_HTML,
        CSS_BASE=CSS_BASE,
        THEME_CSS=get_theme_css(settings["theme"]),
        group=group,
        my_code=code,
        my_nom=user['nom'],
        group_bg=group_bg,
        users=users_data,
        all_contacts=all_contacts,
        central=CENTRAL_SERVER
    )

@app.route('/add_group_members', methods=['POST'])
def add_group_members():
    code, user, db = get_user()
    if not code: return jsonify({"status": "error"}), 403
    data = request.json
    group_id = data.get('group_id')
    new_members = data.get('members', [])
    
    if group_id in db["GROUPS"]:
        for m in new_members:
            if m not in db["GROUPS"][group_id]['members']:
                db["GROUPS"][group_id]['members'].append(m)
        save_db(db)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 404

@app.route('/get_group_msgs/<group_id>')
def get_group_msgs(group_id):
    code, user, db = get_user()
    if not code: return jsonify([]), 403
    msgs = db["GROUP_MSGS"].get(group_id, [])
    return jsonify(msgs)

@app.route('/statuses')
def statuses():
    code, user, db = get_user()
    if not code: return redirect('/')
    cleanup_statuses(db)
    settings = get_user_settings(code, db)
    
    contact_statuses = {}
    relevant_codes = user.get('contacts', []) + [code]
    
    for c in relevant_codes:
        u = db["USERS"].get(c)
        if not u: continue
        st_list = [st for st in db["STATUSES"].values() if st.get('user_code') == c]
        if st_list:
            contact_statuses[c] = {
                "user": {
                    "nom": u['nom'],
                    "photo": u['photo'],
                    "initial": avatar_letter(u['nom']) if not u['photo'] else ''
                },
                "list": st_list
            }

    return render_template_string(
        STATUSES_HTML,
        CSS_BASE=CSS_BASE,
        THEME_CSS=get_theme_css(settings["theme"]),
        contact_statuses=contact_statuses
    )

@app.route('/publish_status', methods=['POST'])
def publish_status():
    code, user, db = get_user()
    if not code: return jsonify({"status": "error"}), 403
    data = request.json
    status_id = "st_" + str(int(time.time() * 1000))
    
    db["STATUSES"][status_id] = {
        "id": status_id,
        "user_code": code,
        "user_nom": user['nom'],
        "media": data.get('media'),
        "type": data.get('type'),
        "text_overlay": data.get('text_overlay', ''),
        "music": data.get('music'),
        "timestamp": time.time()
    }
    save_db(db)
    return jsonify({"status": "ok"})

@app.route('/status_comments_page')
def status_comments_page():
    code, user, db = get_user()
    if not code: return redirect('/')
    settings = get_user_settings(code, db)
    
    comments = []
    my_status_ids = [st_id for st_id, st in db["STATUSES"].items() if st.get('user_code') == code]
    for st_id in my_status_ids:
        if st_id in db["STATUS_COMMENTS"]:
            comments.extend(db["STATUS_COMMENTS"][st_id])
            
    return render_template_string(
        STATUS_COMMENTS_HTML,
        CSS_BASE=CSS_BASE,
        THEME_CSS=get_theme_css(settings["theme"]),
        comments=comments
    )

@app.route('/channels')
def channels():
    code, user, db = get_user()
    if not code: return redirect('/')
    settings = get_user_settings(code, db)
    ch_list = list(db["CHANNELS"].values())
    return render_template_string(
        CHANNELS_HTML,
        CSS_BASE=CSS_BASE,
        THEME_CSS=get_theme_css(settings["theme"]),
        channels=ch_list
    )

@app.route('/create_channel', methods=['POST'])
def create_channel():
    code, user, db = get_user()
    if not code: return jsonify({"status": "error"}), 403
    data = request.json
    ch_id = gen_code_port()
    
    db["CHANNELS"][ch_id] = {
        "id": ch_id,
        "name": data.get('name'),
        "photo": data.get('photo', ''),
        "owner": code,
        "followers": [code]
    }
    db["CHANNEL_MSGS"][ch_id] = []
    save_db(db)
    return jsonify({"status": "ok", "id": ch_id})

@app.route('/channel/<channel_id>')
def channel_view(channel_id):
    code, user, db = get_user()
    if not code: return redirect('/')
    channel = db["CHANNELS"].get(channel_id)
    if not channel: return "Chaîne introuvable", 404
    
    settings = get_user_settings(code, db)
    is_owner = (channel['owner'] == code)
    is_following = code in channel.get('followers', [])
    msgs = db["CHANNEL_MSGS"].get(channel_id, [])
    
    return render_template_string(
        CHANNEL_VIEW_HTML,
        CSS_BASE=CSS_BASE,
        THEME_CSS=get_theme_css(settings["theme"]),
        channel=channel,
        is_owner=is_owner,
        is_following=is_following,
        msgs=msgs,
        my_code=code,
        my_nom=user['nom']
    )

@app.route('/publish_channel_msg', methods=['POST'])
def publish_channel_msg():
    code, user, db = get_user()
    if not code: return jsonify({"status": "error"}), 403
    data = request.json
    ch_id = data.get('channel')
    
    if ch_id in db["CHANNELS"] and db["CHANNELS"][ch_id]['owner'] == code:
        db["CHANNEL_MSGS"][ch_id].append(data)
        save_db(db)
        socketio.emit('receive_channel_message', data, room=ch_id)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 403

@app.route('/toggle_follow_channel', methods=['POST'])
def toggle_follow_channel():
    code, user, db = get_user()
    if not code: return jsonify({"status": "error"}), 403
    data = request.json
    ch_id = data.get('channel_id')
    
    if ch_id in db["CHANNELS"]:
        followers = db["CHANNELS"][ch_id].setdefault('followers', [])
        if code in followers:
            followers.remove(code)
        else:
            followers.append(code)
        save_db(db)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 404

@socketio.on('join')
def on_join(data):
    code = data.get('code')
    if code:
        join_room(code)

@socketio.on('send_message')
def handle_send_message(data):
    db = load_db()
    to_code = data.get('to')
    from_code = data.get('from')
    
    pair_key = "_".join(sorted([from_code, to_code]))
    if pair_key not in db["MESSAGES"]:
        db["MESSAGES"][pair_key] = []
        
    db["MESSAGES"][pair_key].append(data)
    
    if to_code not in db["UNREAD"]:
        db["UNREAD"][to_code] = {}
    db["UNREAD"][to_code][from_code] = db["UNREAD"][to_code].get(from_code, 0) + 1
    
    save_db(db)
    
    emit('receive_message', data, room=to_code)
    emit('new_message_alert', {}, room=to_code)

@socketio.on('send_group_message')
def handle_send_group_message(data):
    db = load_db()
    group_id = data.get('group')
    if group_id in db["GROUPS"]:
        if group_id not in db["GROUP_MSGS"]:
            db["GROUP_MSGS"][group_id] = []
        db["GROUP_MSGS"][group_id].append(data)
        save_db(db)
        emit('receive_group_message', data, room=group_id)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
