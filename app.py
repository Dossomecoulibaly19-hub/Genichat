from flask import Flask, render_template_string, request, redirect, session, url_for, jsonify
from flask_socketio import SocketIO, emit
import json, os, base64, time, random, string
from datetime import datetime
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "genie_v33_whatsapp")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

CENTRAL_SERVER = "https://genie-facteur.onrender.com"
DB_FILE = "genie_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE) as f: return json.load(f)
    return {"USERS": {}, "MESSAGES": {}}

def save_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f)

db = load_db()
USERS = db["USERS"]
MESSAGES = db["MESSAGES"]

def gen_code_port():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

CSS = """* {box-sizing: border-box; margin:0; padding:0; font-family: 'Segoe UI', Roboto, sans-serif;}
body {background:#111B21; color:#E9EDEF;}
.header {background:#202C33; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10;}
.btn {background:#00A884; color:white; border:none; padding:14px 15px; border-radius:10px; cursor:pointer; font-weight:600; width:100%; margin-top:12px; font-size:16px; text-decoration:none; display:block; text-align:center;}
.btn-gray {background:#2A3942;}
.input {padding:14px; border:none; border-radius:10px; background:#2A3942; color:white; width:100%; margin-top:6px; font-size:16px;}
.form-group {margin-bottom:15px;}
.avatar {width:40px; height:40px; border-radius:50%; background:#00A884; display:flex; align-items:center; justify-content:center; font-weight:bold; background-size:cover; background-position:center; color:white;}
.avatar-big {width:150px; height:150px; border-radius:50%; margin:0 auto 20px; display:flex; align-items:center; justify-content:center; background:#2A3942; font-size:60px; font-weight:bold; border:4px solid #00A884; background-size:cover; background-position:center;}
.box {background:#202C33; padding:25px; border-radius:20px; max-width:450px; margin:30px auto; width:90%; box-shadow:0 4px 20px rgba(0,0,0,0.3);}
.code-info {padding:14px; background:#000; font-size:20px; color:#00A884; border-radius:10px; text-align:center; letter-spacing:4px; font-weight:bold; margin:10px 0;}
.contact-list {flex:1; overflow-y:auto;}
.contact{padding:14px 16px; display:flex; align-items:center; gap:14px; cursor:pointer; border-bottom:1px solid #2A3942;}
.contact:hover{background:#2A3942;}
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
"""

LOGIN_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>GenieChat</title><style>{{ CSS }}</style></head><body>
<div class="box"><h2>🙋 GenieChat</h2>
<form method="POST" action="/login" enctype="multipart/form-data">
<div id="preview" class="avatar-big" style="background-image:url('{{photo}}')">{{ '' if photo else '' }}</div>
<label for="photo" class="btn btn-gray">📷 Choisir Photo Profil</label><input type="file" id="photo" name="photo" accept="image/*" style="display:none;">
<input type="hidden" id="crop_x" name="crop_x"><input type="hidden" id="crop_y" name="crop_y"><input type="hidden" id="crop_scale" name="crop_scale"><input type="hidden" id="original_img" name="original_img">
<div class="form-group"><label>Nom d'utilisateur</label><input name="nom" id="nom" class="input" placeholder="Entre ton nom" value="{{nom}}" required></div>
{% if not code %}
<div class="form-group"><label>Code Unique</label><input name="code" id="code" class="input" placeholder="Laisse vide pour créer un nouveau"></div>
<button class="btn">Entrer</button>
{% else %}
<div class="alert">Bienvenue {{nom}}</div><label>TON CODE:</label><div class="code-info">{{ code }}</div>
<a href="/contacts" class="btn">Accéder aux Chats</a>
<a href="/logout" class="btn btn-gray">Changer de Compte</a>
{% endif %}
</form></div>
<div id="cropModal" class="crop-modal"><div class="crop-area"><img id="cropImg" class="crop-img"><div class="crop-circle"></div></div>
<div class="crop-buttons"><button type="button" class="btn btn-gray" onclick="zoom(-0.1)">-</button>
<button type="button" class="btn btn-gray" onclick="closeCrop()">Annuler</button>
<button type="button" class="btn btn-gray" onclick="zoom(0.1)">+</button>
<button type="button" class="btn" onclick="saveCrop()">Valider</button></div></div>
<script>
let scale=1,posX=0,posY=0,isDragging=false,startX,startY;
let cropImg = document.getElementById('cropImg');
let preview = document.getElementById('preview');
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
function getPointerPos(e){ if(e.touches) return {x:e.touches[0].clientX, y:e.touches[0].clientY}; return {x:e.clientX, y:e.clientY}; }
cropImg.addEventListener('pointerdown', e=>{ e.preventDefault(); isDragging=true; let pos = getPointerPos(e); startX = pos.x - posX; startY = pos.y - posY; cropImg.style.cursor = 'grabbing'; })
document.addEventListener('pointermove', e=>{ if(!isDragging) return; e.preventDefault(); let pos = getPointerPos(e); posX = pos.x - startX; posY = pos.y - startY; updateTransform(); })
document.addEventListener('pointerup', ()=>{ isDragging=false; cropImg.style.cursor = 'grab'; })
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

CONTACTS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chats</title><style>{{ CSS }}</style></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><h2>Chats</h2><a href="/"><div class="avatar" style="background-image:url('{{ photo }}')">{{ '' if photo else nom[0]|upper }}</div></a></div>
<div class="contact-list">{% for c in contacts %}
<div class="contact" onclick="location='/chat/{{ c }}'">
<div class="avatar" style="background-image:url('{{ users[c].photo }}')">{{ '' if users[c].photo else users[c].nom[0]|upper }}</div>
<div><b>{{ users[c].nom }}</b><br><small style="color:#8696A0;">{{ c }}</small></div></div>{% endfor %}</div>
<div class="add-bar"><form method="POST" action="/ajouter" style="display:flex; width:100%; gap:10px;">
<input name="code_ami" placeholder="Entrer CODE de l'ami" class="input" required><button class="btn" style="width:80px;">Créer</button></form></div>
</body></html>"""

CHAT_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chat avec {{ ami.nom }}</title><style>{{ CSS }}</style><script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script></head><body style="display:flex; flex-direction:column; height:100vh;">
<div class="header"><a href="/contacts" style="color:white; font-size:24px;">←</a>
<div class="avatar" style="background-image:url('{{ ami.photo }}')">{{ '' if ami.photo else ami.nom[0]|upper }}</div>
<div><b>{{ ami.nom }}</b><br><small style="color:#8696A0;">{{ code_ami }}</small></div></div>
<div class="messages" id="msgBox"></div>
<form class="send-box" id="sendForm">
<input type="text" id="message" placeholder="Écris un message" class="input" required>
<button class="btn" style="border-radius:50%; width:48px; height:48px; padding:0; font-size:20px;">➤</button></form>
<script>
const socket=io();const MY_CODE="{{ my_code }}";const AMI_CODE="{{ code_ami }}";
socket.on('connect',()=>socket.emit('join',{code:MY_CODE}));
function load(){fetch('/get_msg/'+AMI_CODE).then(r=>r.json()).then(msgs=>{document.getElementById('msgBox').innerHTML='';
msgs.forEach(m=>addMsg(m.from_nom,m.msg,m.from==MY_CODE,m.time,m.status,m.id));scroll();})}
load();
document.getElementById('sendForm').onsubmit=e=>{e.preventDefault();const msg=document.getElementById('message').value;if(!msg)return;
let t=new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});let id='m'+Date.now();
addMsg("{{ my_nom }}",msg,true,t,'sent',id);
socket.emit('send_message',{to:AMI_CODE,from:MY_CODE,from_nom:"{{ my_nom }}",msg:msg,time:t,id:id});
document.getElementById('message').value='';scroll();}
function addMsg(from,msg,me,time,status,id){let d=document.createElement('div');d.id=id;d.className='msg '+(me?'me':'you');
let check = me? (status=='read'?'<span class="check blue">✓</span>':'<span class="check gray">✓</span>') : '';
d.innerHTML=`${msg}<div class="time">${time} ${check}</div>`;document.getElementById('msgBox').append(d);}
function scroll(){let box=document.getElementById('msgBox');box.scrollTop=box.scrollHeight;}
socket.on('receive_message',d=>{if(d.from==AMI_CODE){addMsg(d.from_nom,d.msg,false,d.time,'read',d.id);scroll();}});
</script></body></html>"""

def get_user():
    code = session.get('code')
    return code, USERS.get(code)

@app.route('/')
def login():
    code, user = get_user()
    return render_template_string(LOGIN_HTML, CSS=CSS, code=code, nom=user['nom'] if user else "", photo=user['photo'] if user else "")

@app.route('/login', methods=['GET','POST'])
def do_login():
    if request.method == 'GET': return redirect('/')
    nom = request.form['nom']
    code = request.form['code'].upper() if request.form['code'] else gen_code_port()
    photo = ""
    if request.form.get('original_img'):
        try:
            x=float(request.form.get('crop_x','0')); y=float(request.form.get('crop_y','0')); s=float(request.form.get('crop_scale','1'))
            img = Image.open(BytesIO(base64.b64decode(request.form['original_img'].split(',')[1])))
            size=200; cx=img.width/2; cy=img.height/2; left=cx-(size/2)/s-x/s; top=cy-(size/2)/s-y/s; right=cx+(size/2)/s-x/s; bottom=cy+(size/2)/s-y/s
            img = img.crop((left,top,right,bottom)).resize((150,150), Image.LANCZOS)
            buf = BytesIO(); img.save(buf, format="PNG")
            photo = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        except: pass
    if code not in USERS:
        USERS[code] = {"nom": nom, "photo": photo, "contacts": []}
    else:
        USERS[code]['nom'] = nom
        if photo: USERS[code]['photo'] = photo
    save_db({"USERS": USERS, "MESSAGES": MESSAGES})
    session['code'] = code
    return redirect('/')

@app.route('/logout')
def logout():
    session.pop('code', None)
    return redirect('/')

@app.route('/contacts')
def contacts():
    code, user = get_user()
    if not code: return redirect('/')
    return render_template_string(CONTACTS_HTML, CSS=CSS, nom=user['nom'], photo=user['photo'], users=USERS, contacts=user['contacts'])

@app.route('/ajouter', methods=['POST'])
def ajouter():
    code, user = get_user()
    if not code: return redirect('/')
    code_ami = request.form['code_ami'].upper().strip()
    if code_ami in USERS:
        if code_ami not in user['contacts']: user['contacts'].append(code_ami)
        if code not in USERS[code_ami]['contacts']: USERS[code_ami]['contacts'].append(code)
        save_db({"USERS": USERS, "MESSAGES": MESSAGES})
        return redirect(f'/chat/{code_ami}')
    else:
        return "Code introuvable", 404

@app.route('/chat/<code_ami>')
def chat(code_ami):
    code, user = get_user()
    if not code: return redirect('/')
    ami = USERS.get(code_ami)
    if not ami: return "Contact introuvable", 404
    return render_template_string(CHAT_HTML, CSS=CSS, code_ami=code_ami, ami=ami, my_code=code, my_nom=user['nom'])

@app.route('/get_msg/<ami>')
def get_msg(ami):
    code, _ = get_user()
    cle = "-".join(sorted([code, ami]))
    return jsonify(MESSAGES.get(cle, []))

@socketio.on('send_message')
def receive(data):
    cle = "-".join(sorted([data['from'], data['to']]))
    if cle not in MESSAGES: MESSAGES[cle] = []
    MESSAGES[cle].append(data)
    save_db({"USERS": USERS, "MESSAGES": MESSAGES})
    emit('receive_message', data, broadcast=True)

if __name__=='__main__':
    port = int(os.environ.get("PORT", 10000))
    socketio.run(app,host='0.0.0.0',port=port)
