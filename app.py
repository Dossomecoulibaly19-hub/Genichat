from flask import Flask, render_template_string, request, redirect, session, jsonify
from flask_socketio import SocketIO, emit, join_room
import json, os, base64, random, string
from io import BytesIO
from PIL import Image

app = Flask(__name__)
app.secret_key = "genie_v33_whatsapp"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

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
body {background:#111B21; color:#E9EDEF;}.header {background:#202C33; padding:12px 16px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0;}
.btn {background:#00A884; color:white; border:none; padding:14px; border-radius:10px; cursor:pointer; font-weight:600; width:100%; margin-top:12px; font-size:16px; text-decoration:none; display:block; text-align:center;}
.btn-gray {background:#2A3942;}
.input {padding:14px; border:none; border-radius:10px; background:#2A3942; color:white; width:100%; margin-top:6px; font-size:16px;}
.form-group {margin-bottom:15px;}
.avatar {width:40px; height:40px; border-radius:50%; background:#00A884; display:flex; align-items:center; justify-content:center; font-weight:bold; background-size:cover; background-position:center; color:white; cursor:pointer;}
.avatar-big {width:150px; height:150px; border-radius:50%; margin:0 auto 20px; display:flex; align-items:center; justify-content:center; background:#2A3942; font-size:60px; font-weight:bold; border:4px solid #00A884; background-size:cover; background-position:center;}
.box {background:#202C33; padding:25px; border-radius:20px; max-width:450px; margin:30px auto; width:90%;}
.code-info {padding:14px; background:#000; font-size:20px; color:#00A884; border-radius:10px; text-align:center; letter-spacing:4px; font-weight:bold; margin:10px 0; user-select:all;}
.contact-list {flex:1; overflow-y:auto;}
.contact{padding:14px 16px; display:flex; align-items:center; gap:14px; cursor:pointer; border-bottom:1px solid #2A3942;}
.messages{padding:15px; flex:1; overflow-y:auto; background:#0B141A; display:flex; flex-direction:column;}
.msg{padding:9px 13px; border-radius:8px; margin:5px 0; max-width:78%; font-size:15px;}
.msg.me{background:#005C4B; align-self:flex-end;}.msg.you{background:#202C33; align-self:flex-start;}
.time{font-size:11px; color:#8696A0; text-align:right; margin-top:4px;}
.send-box{display:flex; padding:10px; background:#202C33; gap:10px; align-items:center;}
.badge{background:#00A884; color:white; border-radius:50%; min-width:22px; height:22px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:bold; padding:2px 6px;}
.crop-modal {display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:#000; z-index:99; flex-direction:column; justify-content:center; align-items:center;}
.crop-area {position:relative; width:100%; height:100%; display:flex; justify-content:center; align-items:center; overflow:hidden;}
.crop-circle {position:absolute; width:200px; height:200px; border:4px solid #00A884; border-radius:50%; box-shadow:0 0 0 9999px rgba(0,0,0,0.8);}
.crop-img {position:absolute; left:50%; top:50%;}
.crop-buttons {position:absolute; bottom:0; width:100%; padding:15px; background:#202C33; display:flex; gap:10px;}
"""

LOGIN_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>GenieChat</title><style>{{ CSS }}</style></head><body>
<div class="box"><h2>👋 GenieChat</h2>{% if code and nom %}
<div class="alert">Bienvenue {{nom}}</div><label>TON CODE:</label><div class="code-info">{{ code }}</div>
<a href="/contacts" class="btn">Accéder aux Chats</a><a href="/logout" class="btn btn-gray">Changer de Compte</a>
{% else %}
<form method="POST" action="/login"><div class="form-group"><label>Code Unique</label><input name="code" class="input" placeholder="Entre ton code" required></div>
<button class="btn">Se Connecter</button></form>
<p style="text-align:center; margin-top:15px;"><a href="/register" style="color:#00A884;">Créer un compte</a></p>{% endif %}</div></body></html>"""

REGISTER_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Créer Compte</title><style>{{ CSS }}</style></head><body>
<div class="box"><h2>Créer ton Compte</h2>
<form method="POST" action="/register" id="regForm"><input type="hidden" name="original_img" id="original_img">
<div id="preview" class="avatar-big" onclick="document.getElementById('fileInput').click()">{{ '' }}</div>
<input type="file" id="fileInput" accept="image/*" style="display:none;">
<div class="form-group"><label>Nom</label><input name="nom" class="input" required></div><button class="btn">Créer</button>
</form><a href="/" class="btn btn-gray">Déjà un compte?</a></div>
<div id="cropModal" class="crop-modal"><div class="crop-area"><img id="cropImage" class="crop-img"><div class="crop-circle"></div></div><div class="crop-buttons"><button type="button" class="btn btn-gray" onclick="closeCrop()">Annuler</button><button type="button" class="btn" onclick="applyCrop()">Valider</button></div></div>
<script>
let cropperImg=document.getElementById('cropImage');let scale=1;let posX=0;let posY=0;let isDragging=false;let startX,startY;
document.getElementById('fileInput').onchange=e=>{let file=e.target.files[0];if(!file)return;let reader=new FileReader();
reader.onload=ev=>{cropperImg.src=ev.target.result;document.getElementById('cropModal').style.display='flex';};reader.readAsDataURL(file);};
function closeCrop(){document.getElementById('cropModal').style.display='none';}
function applyCrop(){let canvas=document.createElement('canvas');canvas.width=150;canvas.height=150;let ctx=canvas.getContext('2d');
ctx.drawImage(cropperImg,-posX,-posY,150*scale,150*scale);let dataURL=canvas.toDataURL('image/png');
document.getElementById('preview').style.backgroundImage=`url(${dataURL})`;document.getElementById('original_img').value=dataURL;closeCrop();}
</script></body></html>"""

SETTINGS_HTML = """<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Paramètres</title><style>{{ CSS }}</style></head><body>
<div class="header"><a href="/contacts" style="font-size:24px;">←</a><h2>Profil</h2><div></div></div>
<div class="box">
<label>TON CODE:</label><div class="code-info">{{ code }}</div>
<form method="POST" action="/update_profile" id="settingsForm"><input type="hidden" name="original_img" id="original_img" value="{{ photo }}">
<div id="preview" class="avatar-big" style="background-image:url('{{ photo }}')" onclick="document.getElementById('fileInput').click()">{{ nom[0]|upper }}</div>
<input type="file" id="fileInput" accept="image/*" style="display:none;">
<div class="form-group"><label>Nom</label><input name="nom" value="{{ nom }}" class="input" required></div><button class="btn">Enregistrer</button>
</form></div>
<div id="cropModal" class="crop-modal"><div class="crop-area"><img id="cropImage" class="crop-img"><div class="crop-circle"></div></div><div class="crop-buttons"><button type="button" class="btn btn-gray" onclick="closeCrop()">Annuler</button><button type="button" class="btn" onclick="applyCrop()">Valider</button></div></div>
<script>
let cropperImg=document.getElementById('cropImage');let scale=1;let posX=0;let posY=0;
document.getElementById('fileInput').onchange=e=>{let file=e.target.files[0];if(!file)return;let reader=new FileReader();
reader.onload=ev=>{cropperImg.src=ev.target.result;document.getElementById('cropModal').style.display='flex';};reader.readAsDataURL(file);};
function closeCrop(){document.getElementById('cropModal').style.display='none';}
function applyCrop(){let canvas=document.createElement('canvas');canvas.width=150;canvas.height=150;let ctx=canvas.getContext('2d');
ctx.drawImage(cropperImg,-posX,-posY,150*scale,150*scale);let dataURL=canvas.toDataURL('image/png');
document.getElementById('preview').style.backgroundImage=`url(${dataURL})`;document.getElementById('original_img').value=dataURL;closeCrop();}
</script></body></html>"""

CONTACTS_HTML = """...""" # Ton code contacts ici
CHAT_HTML = """...""" # Ton code chat ici

def get_user():
    code = session.get('code'); db = load_db()
    return code, db["USERS"].get(code), db

@app.route('/')
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        db=load_db(); code=request.form['code'].upper();
        if code in db["USERS"]: session['code']=code; return redirect('/')
    code,user,db=get_user()
    return render_template_string(LOGIN_HTML, CSS=CSS, code=code, nom=user['nom'] if user else None)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='GET': return render_template_string(REGISTER_HTML, CSS=CSS)
    db=load_db(); nom=request.form['nom']; code=gen_code_port(); photo=""
    if request.form.get('original_img'):
        img=Image.open(BytesIO(base64.b64decode(request.form['original_img'].split(',')[1]))).resize((150,150))
        buf=BytesIO(); img.save(buf,format="PNG"); photo="data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()
    db["USERS"][code]={"nom":nom,"photo":photo,"contacts":[]}; save_db(db); session['code']=code; return redirect('/')

@app.route('/settings')
def settings():
    code,user,db=get_user();
    return render_template_string(SETTINGS_HTML, CSS=CSS, nom=user['nom'], photo=user['photo'], code=code)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    code,user,db=get_user(); user['nom']=request.form['nom']
    if request.form.get('original_img'):
        img=Image.open(BytesIO(base64.b64decode(request.form['original_img'].split(',')[1]))).resize((150,150))
        buf=BytesIO(); img.save(buf,format="PNG"); user['photo']="data:image/png;base64,"+base64.b64encode(buf.getvalue()).decode()
    db["USERS"][code]=user; save_db(db); return redirect('/settings')

@app.route('/logout')
def logout():
    session.pop('code',None);
    return redirect('/')

#... le reste de tes routes socketio...

if __name__=='__main__':
    socketio.run(app,host='0.0.0.0',port=int(os.environ.get("PORT", 10000)), allow_unsafe_werkzeug=True)
