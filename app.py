from flask import Flask, render_template_string, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit, join_room
import json, os, random, string

app = Flask(__name__)
app.secret_key = "genie_v35_offline"
socketio = SocketIO(app, cors_allowed_origins="*")

CENTRAL_SERVER = "https://genie-facteur.onrender.com"
DB_FILE = "genie_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return json.load(f)
    return {"USERS": {}, "MESSAGES": {}, "UNREAD": {}}

def save_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f)

def gen_code_port(): return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

CSS = """* {box-sizing: border-box; margin:0; padding:0; font-family: 'Segoe UI', Roboto, sans-serif;}
body {background:#111B21; color:#E9EDEF;}
.header {background:#202C33; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10;}
.btn {background:#00A884; color:white; border:none; padding:14px; border-radius:10px; cursor:pointer; font-weight:600; width:100%; margin-top:12px; font-size:16px; text-decoration:none; display:block; text-align:center;}
.btn-gray {background:#2A3942;}
.input {padding:14px; border:none; border-radius:10px; background:#2A3942; color:white; width:100%; margin-top:6px; font-size:16px;}
.form-group {margin-bottom:15px;}
.avatar {width:40px; height:40px; border-radius:50%; background:#00A884; display:flex; align-items:center; justify-content:center; font-weight:bold; background-size:cover; background-position:center; color:white; cursor:pointer; flex-shrink:0;}
.avatar-big {width:150px; height:150px; border-radius:50%; margin:0 auto 20px; display:flex; align-items:center; justify-content:center; background:#2A3942; font-size:60px; font-weight:bold; border:4px solid #00A884; background-size:cover; background-position:center; cursor:pointer; overflow:hidden;}
.box {background:#202C33; padding:25px; border-radius:20px; max-width:450px; margin:30px auto; width:90%;}
.code-info {padding:14px; background:#000; font-size:20px; color:#00A884; border-radius:10px; text-align:center; letter-spacing:4px; font-weight:bold; margin:10px 0; user-select:all;}
.contact-list {flex:1; overflow-y:auto;}
.contact{padding:14px 16px; display:flex; align-items:center; gap:14px; cursor:pointer; border-bottom:1px solid #2A3942;}
.messages{padding:15px; flex:1; overflow-y:auto; background:#0B141A; display:flex; flex-direction:column;}
.msg{padding:9px 13px; border-radius:8px; margin:5px 0; max-width:78%; font-size:15px; word-wrap:break-word;}
.msg.me{background:#005C4B; align-self:flex-end;}.msg.you{background:#202C33; align-self:flex-start;}
.time{font-size:11px; color:#8696A0; text-align:right; margin-top:4px;}
.send-box{display:flex; padding:10px; background:#202C33; gap:10px; align-items:center;}
.badge{background:#00A884; color:white; border-radius:50%; min-width:22px; height:22px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:bold; padding:2px 6px;}
.crop-modal {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:#000; z-index:99; flex-direction:column; justify-content:center; align-items:center;}
.crop-area {position:relative; width:100%; height:70vh; display:flex; justify-content:center; align-items:center; overflow:hidden; background:#111; touch-action:none;}
.crop-circle {position:absolute; width:200px; height:200px; border:4px solid #00A884; border-radius:50%; box-shadow:0 0 0 9999px rgba(0,0,0,0.7); pointer-events:none; z-index:2;}
.crop-img {position:absolute; left:50%; top:50%; transform-origin:center center; cursor:grab; z-index:1; max-width:none; max-height:none;}
.crop-img:active {cursor:grabbing;}
.crop-buttons {position:absolute; bottom:0; width:100%; padding:15px; background:#202C33; display:flex; gap:10px; z-index:3;}
.add-bar {padding:10px; background:#202C33; display:flex;}
.alert {background:#00A884; padding:10px; border-radius:10px; margin-bottom:15px; text-align:center;}
.last-msg {font-size:13px; color:#8696A0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:200px;}
"""

JS_CROP = """
let scale=1,posX=0,posY=0,isDragging=false,startX=0,startY=0;
const cropImg = document.getElementById('cropImg'); const preview = document.getElementById('preview'); 
document.getElementById('photo').onchange = function(e){
    const file=e.target.files[0]; if(!file) return;
    const reader=new FileReader();
    reader.onload=function(ev){
        cropImg.src = ev.target.result;
        document.getElementById('cropModal').style.display='flex';
        cropImg.onload = ()=>{ scale=1; posX=0; posY=0; fitImage(); }
    }
    reader.readAsDataURL(file);
}
function fitImage(){
    const area = document.querySelector('.crop-area');
    const ratio = Math.max(200/cropImg.naturalWidth, 200/cropImg.naturalHeight);
    scale = ratio; updateTransform();
}
function updateTransform(){cropImg.style.transform=`translate(-50%,-50%) translate(${posX}px,${posY}px) scale(${scale})`;}
function getPointerPos(e){return e.touches? e.touches[0] : e;}
cropImg.onpointerdown = cropImg.ontouchstart = e=>{isDragging=true; const p=getPointerPos(e); startX = p.clientX - posX; startY = p.clientY - posY;};
document.onpointermove = document.ontouchmove = e=>{if(!isDragging) return; e.preventDefault(); const p=getPointerPos(e); posX = p.clientX - startX; posY = p.clientY - startY; updateTransform();}
document.onpointerup = document.ontouchend = ()=>{isDragging=false;}
function zoom(v){scale+=v; if(scale<0.5)scale=0.5; if(scale>5)scale=5; updateTransform();}
function closeCrop(){document.getElementById('cropModal').style.display='none';}
function saveCrop(){
    let canvas=document.createElement('canvas');canvas.width=150;canvas.height=150;let ctx=canvas.getContext('2d');
    ctx.beginPath();ctx.arc(75,75,75,0,Math.PI*2);ctx.clip();
    const displayWidth = cropImg.naturalWidth * scale;
    const displayHeight = cropImg.naturalHeight * scale;
    const dx = 75 - displayWidth/2 + posX;
    const dy = 75 - displayHeight/2 + posY;
    ctx.drawImage(cropImg, dx, dy, displayWidth, displayHeight);
    let dataURL=canvas.toDataURL('image/jpeg', 0.9);
    document.getElementById('photo_data').value=dataURL;
    preview.style.backgroundImage = `url(${dataURL})`;
    preview.innerHTML = '';
    closeCrop();
}
"""

LOGIN_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>GenieChat</title><style>{{ CSS }}</style></head><body>
<div class="box"><h2>👋 GenieChat</h2>{% if code and nom %}
<div class="alert">Bienvenue {{nom}}</div><label>TON CODE:</label><div class="code-info">{{ code }}</div>
<a href="/contacts" class="btn">Accéder aux Chats</a><a href="/logout" class="btn btn-gray">Changer de Compte</a>
{% else %}
<form method="POST" action="/login"><div class="form-group"><label>Code Unique</label><input name="code" class="input" placeholder="Entre ton code" required></div>
<button class="btn">Se Connecter</button></form>
<p style="text-align:center; margin-top:15px;"><a href="/register" style="color:#00A884;">Créer un compte</a></p>{% endif %}</div>
<script>
// Si on a un code en local, on propose de se reconnecter auto
const savedCode = localStorage.getItem('genie_code');
if(savedCode &&!window.location.search.includes('logout')){
    document.querySelector('input[name=code]').value = savedCode;
}
document.querySelector('form')?.addEventListener('submit', ()=>{
    localStorage.setItem('genie_code', document.querySelector('input[name=code]').value.toUpperCase());
});
</script>
</body></html>"""

REGISTER_HTML = f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Créer Compte</title><style>{CSS}</style></head><body>
<div class="box"><h2>Créer ton Compte</h2>
<form method="POST" action="/register"><input type="hidden" id="photo_data" name="photo_data">
<div id="preview" class="avatar-big">+</div>
<label for="photo" class="btn btn-gray">📷 Choisir Photo</label><input type="file" id="photo" accept="image/*" style="display:none;">
<div class="form-group"><label>Nom</label><input name="nom" class="input" required></div><button class="btn">Créer</button>
</form><a href="/" class="btn btn-gray">Déjà un compte?</a></div>
<div id="cropModal" class="crop-modal"><div class="crop-area"><img id="cropImg" class="crop-img"><div class="crop-circle"></div></div>
<div class="crop-buttons"><button type="button" class="btn btn-gray" onclick="zoom(-0.2)">-</button><button type="button" class="btn btn-gray" onclick="closeCrop()">Annuler</button><button type="button" class="btn btn-gray" onclick="zoom(0.2)">+</button><button type="button" class="btn" onclick="saveCrop()">Valider</button></div></div>
<script>{JS_CROP}</script></body></html>"""

SETTINGS_HTML = f"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Paramètres</title><style>{CSS}</style></head><body>
<div class="header"><a href="/contacts" style="font-size:24px;">←</a><h2>Profil</h2><div></div></div>
<div class="box">
<label>TON CODE:</label><div class="code-info">{{ code }}</div>
<form method="POST" action="/update_profile"><input type="hidden" id="photo_data" name="photo_data" value="{{ photo }}">
<div id="preview" class="avatar-big" style="{{ 'background-image:url('+photo+')' if photo else '' }}">{{ '' if photo else nom[0]|upper }}</div>
<label for="photo" class="btn btn-gray">📷 Changer Photo</label><input type="file" id="photo" accept="image/*" style="display:none;">
<div class="form-group"><label>Nom</label><input name="nom" value="{{ nom }}" class="input" required></div><button class="btn">Enregistrer</button>
</form></div>
<div id="cropModal" class="crop-modal"><div class="crop-area"><img id="cropImg" class="crop-img"><div class="crop-circle"></div></div>
<div class="crop-buttons"><button type="button" class="btn btn-gray" onclick="zoom(-0.2)">-</button><button type="button" class="btn btn-gray" onclick="closeCrop()">Annuler</button><button type="button" class="btn btn-gray" onclick="zoom(0.2)">+</button><button type="button" class="btn" onclick="saveCrop()">Valider</button></div></div>
<script>{JS_CROP}</script></body></html>"""

CONTACTS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Chats</title><style>{{ CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><h2>Chats</h2><a href="/settings"><div class="avatar" style="{{ 'background-image:url('+photo+')' if photo else '' }}">{{ '' if photo else nom[0]|upper }}</div></a></div>
<div class="contact-list" id="contact-list">Chargement...</div>
<div class="add-bar"><form method="POST" action="/ajouter" style="display:flex; width:100%; gap:10px;"><input name="code_ami" placeholder="CODE de l'ami" class="input" required><button class="btn" style="width:80px;">Créer</button></form></div>
<script>
const socket=io("{{ central }}"); const MY_CODE="{{ my_code }}";
socket.emit('join',{code:MY_CODE});

// 1. TELECHARGER TOUS LES MESSAGES AU DEMARRAGE
function syncAllMessages(contacts){
    contacts.forEach(c=>{
        const key = `chat_${MY_CODE}_${c}`;
        fetch(`/get_msg/${c}`).then(r=>r.json()).then(msgs=>{
            localStorage.setItem(key, JSON.stringify(msgs));
        });
    });
}

function renderContacts(data){
    localStorage.setItem('genie_users', JSON.stringify(data.users)); // Sauvegarde users
    syncAllMessages(data.contacts); // Télécharge tout
    
    let html=''; for(let c of data.contacts){
        if(!data.users[c]) continue;
        const key = `chat_${MY_CODE}_${c}`;
        const msgs = JSON.parse(localStorage.getItem(key) || '[]');
        const lastMsg = msgs.length > 0? msgs[msgs.length-1].msg : 'Nouveau contact';
        
        html+=`<div class="contact" onclick="location='/chat/${c}'">
        <div class="avatar" style="${data.users[c].photo?`background-image:url('${data.users[c].photo}')`:''}">${data.users[c].photo?'':data.users[c].nom[0]}</div>
        <div style="flex:1;">
            <b>${data.users[c].nom}</b>
            <div class="last-msg">${lastMsg}</div>
        </div>
        ${data.unread[c]>0?`<div class="badge">${data.unread[c]}</div>`:''}
        </div>`
    } document.getElementById('contact-list').innerHTML=html || '<p style="text-align:center; padding:20px; color:#8696A0;">Aucun contact. Ajoute un code.</p>';
}

fetch('/api/contacts').then(r=>r.json()).then(renderContacts);
socket.on('new_message_alert', ()=>fetch('/api/contacts').then(r=>r.json()).then(renderContacts));
</script></body></html>"""

CHAT_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Chat</title><style>{{ CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><a href="/contacts" style="font-size:24px;">←</a><div class="avatar" style="{{ 'background-image:url('+ami.photo+')' if ami.photo else '' }}">{{ '' if ami.photo else ami.nom[0]|upper }}</div><div><b>{{ ami.nom }}</b><br><small>{{ code_ami }}</small></div></div>
<div class="messages" id="msgBox"></div>
<form class="send-box" id="sendForm"><input type="text" id="message" placeholder="Écris un message" class="input" autocomplete="off"><button class="btn" style="border-radius:50%; width:48px; height:48px; padding:0;">➤</button></form>
<script>
const socket=io("{{ central }}");const MY_CODE="{{ my_code }}";const AMI_CODE="{{ code_ami }}";const STORAGE_KEY=`chat_${MY_CODE}_${AMI_CODE}`;
socket.emit('join',{code:MY_CODE});
const msgBox = document.getElementById('msgBox');

function saveLocal(msgs){localStorage.setItem(STORAGE_KEY, JSON.stringify(msgs));}
function loadLocal(){return JSON.parse(localStorage.getItem(STORAGE_KEY)||'[]');}
function addMsg(m,me){let d=document.createElement('div');d.className='msg '+(me?'me':'you');d.innerHTML=`${m.msg}<div class="time">${m.time}</div>`;msgBox.append(d); msgBox.scrollTop = msgBox.scrollHeight;}
function loadAll(){msgBox.innerHTML=''; let msgs = loadLocal(); msgs.forEach(m=>addMsg(m, m.from==MY_CODE));}

loadAll(); // Affiche direct ce qu'on a en local
fetch('/get_msg/'+AMI_CODE).then(r=>r.json()).then(serverMsgs=>{ // Puis met à jour
    if(JSON.stringify(serverMsgs)!== JSON.stringify(loadLocal())){
        saveLocal(serverMsgs); loadAll();
    }
});

document.getElementById('sendForm').onsubmit=e=>{e.preventDefault();const msg=document.getElementById('message').value.trim();if(!msg)return;
let t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});let data={to:AMI_CODE,from:MY_CODE,from_nom:"{{ my_nom }}",msg:msg,time:t};
let local = loadLocal(); local.push(data); saveLocal(local); addMsg(data,true);
socket.emit('send_message',data); document.getElementById('message').value='';}

socket.on('receive_message',d=>{ if(d.from==AMI_CODE){let local = loadLocal(); local.push(d); saveLocal(local); addMsg(d,false);} });
</script></body></html>"""

def get_user():
    code = session.get('code'); db = load_db()
    return code, db["USERS"].get(code), db

@app.route('/')
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        db=load_db(); code=request.form['code'].upper();
        if code in db["USERS"]: session['code']=code; return redirect('/contacts')
    code,user,db=get_user()
    return render_template_string(LOGIN_HTML, CSS=CSS, code=code, nom=user['nom'] if user else None)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='GET': return render_template_string(REGISTER_HTML)
    db=load_db(); nom=request.form['nom']; code=gen_code_port(); photo=request.form.get('photo_data',"")
    db["USERS"][code]={"nom":nom,"photo":photo,"contacts":[]}; save_db(db); session['code']=code; return redirect('/contacts')

@app.route('/settings')
def settings(): code,user,db=get_user(); return render_template_string(SETTINGS_HTML, nom=user['nom'], photo=user['photo'], code=code)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    code,user,db=get_user(); user['nom']=request.form['nom']; user['photo']=request.form.get('photo_data',user['photo'])
    db["USERS"][code]=user; save_db(db); return redirect('/contacts')

@app.route('/logout')
def logout(): session.pop('code',None); return redirect('/?logout=1')

@app.route('/contacts')
def contacts(): code,user,db=get_user(); return render_template_string(CONTACTS_HTML, CSS=CSS, photo=user['photo'], nom=user['nom'], my_code=code, central=CENTRAL_SERVER)

@app.route('/api/contacts')
def api_contacts(): 
    code,user,db=get_user()
    return jsonify({"users":db["USERS"],"contacts":user['contacts'],"unread":db["UNREAD"].get(code,{})

@app.route('/ajouter', methods=['POST'])
def ajouter(): 
    code,user,db=get_user(); code_ami=request.form['code_ami'].upper();
    if code_ami in db["USERS"]:
        if code_ami not in user['contacts']: user['contacts'].append(code_ami)
        if code not in db["USERS"][code_ami]['contacts']: db["USERS"][code_ami]['contacts'].append(code)
        db["USERS"][code]=user; save_db(db)
    return redirect(f'/chat/{code_ami}')

@app.route('/chat/<code_ami>')
def chat(code_ami): 
    code,user,db=get_user(); ami=db["USERS"].get(code_ami);
    if code in db["UNREAD"] and code_ami in db["UNREAD"][code]: db["UNREAD"][code][code_ami]=0; save_db(db)
    return render_template_string(CHAT_HTML, CSS=CSS, central=CENTRAL_SERVER, code_ami=code_ami, ami=ami, my_code=code, my_nom=user['nom'])

@app.route('/get_msg/<ami>')
def get_msg(ami): code,_,db=get_user(); cle="-".join(sorted([code,ami])); return jsonify(db["MESSAGES"].get(cle,[]))

@socketio.on('join')
def on_join(data): join_room(data['code'])

@socketio.on('send_message')
def handle_send(data):
    db=load_db(); cle="-".join(sorted([data['to'],data['from']]))
    if cle not in db["MESSAGES"]: db["MESSAGES"][cle]=[]
    db["MESSAGES"][cle].append(data)
    if data['to'] not in db["UNREAD"]: db["UNREAD"][data['to']]={}
    db["UNREAD"][data['to']][data['from']]=db["UNREAD"][data['to']].get(data['from'],0)+1
    save_db(db)
    emit('receive_message',data,room=data['to']); emit('new_message_alert',{},room=data['to'])

if __name__=='__main__': 
    socketio.run(app,host='0.0.0.0',port=int(os.environ.get("PORT", 10000)), allow_unsafe_werkzeug=True)
