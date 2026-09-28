import os
import sys
import subprocess
import tempfile
import shutil
import ast
import json
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-render-v3'

# Base de données
db_url = os.environ.get('DATABASE_URL', 'sqlite:///editor.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    files_json = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()

running_processes = {}

@app.route('/')
def index():
    projects = Project.query.all()
    return render_template('index.html', projects=projects)

@app.route('/syntax_check', methods=['POST'])
def syntax_check():
    data = request.json or {}
    code = data.get('code', '')
    filename = data.get('filename', 'main.py')
    
    try:
        ast.parse(code, filename=filename)
        return jsonify({'valid': True})
    except SyntaxError as e:
        return jsonify({
            'valid': False,
            'line': e.lineno or 1,
            'column': e.offset or 1,
            'msg': e.msg,
            'text': e.text or ''
        })
    except Exception as e:
        return jsonify({'valid': False, 'line': 1, 'column': 1, 'msg': str(e), 'text': ''})

@app.route('/install_package', methods=['POST'])
def install_package():
    data = request.json or {}
    package = data.get('package', '').strip()
    if not package:
        return jsonify({'output': 'Nom de package invalide.'}), 400
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'pip', 'install', package],
            capture_output=True,
            text=True,
            timeout=60
        )
        return jsonify({'output': result.stdout + result.stderr})
    except Exception as e:
        return jsonify({'output': str(e)})

@app.route('/save_project', methods=['POST'])
def save_project():
    data = request.json or {}
    name = data.get('name', 'Mon Projet')
    files = data.get('files', {})
    files_json = json.dumps(files)
    
    project = Project.query.filter_by(name=name).first()
    if project:
        project.files_json = files_json
    else:
        project = Project(name=name, files_json=files_json)
        db.session.add(project)
    
    db.session.commit()
    return jsonify({'status': 'success', 'id': project.id})

@app.route('/load_project/<int:project_id>')
def load_project(project_id):
    project = Project.query.get_or_404(project_id)
    return jsonify({'name': project.name, 'files': json.loads(project.files_json)})

# WebSockets pour l'exécution fluide
@socketio.on('start_execution')
def handle_start_execution(data):
    sid = request.sid
    files = data.get('files', {})
    entrypoint = data.get('entrypoint', 'main.py')
    
    if entrypoint not in files:
        emit('output', {'data': f"Erreur: Le fichier d'entrée '{entrypoint}' n'existe pas.\n", 'type': 'stderr'})
        emit('execution_finished', {'code': 1})
        return

    temp_dir = tempfile.mkdtemp(prefix="py_exec_")
    
    for filename, content in files.items():
        filepath = os.path.join(temp_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
            
    exec_file = os.path.join(temp_dir, entrypoint)
    
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        proc = subprocess.Popen(
            [sys.executable, '-u', exec_file],
            cwd=temp_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            env=env
        )
        running_processes[sid] = {'proc': proc, 'temp_dir': temp_dir}

        def read_output():
            while True:
                chunk = proc.stdout.read(1)
                if chunk == b'' and proc.poll() is not None:
                    break
                if chunk:
                    text = chunk.decode('utf-8', errors='replace')
                    socketio.emit('output', {'data': text, 'type': 'stdout'}, room=sid)
            
            returncode = proc.wait()
            shutil.rmtree(temp_dir, ignore_errors=True)
            socketio.emit('execution_finished', {'code': returncode}, room=sid)
            if sid in running_processes:
                del running_processes[sid]

        socketio.start_background_task(target=read_output)

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        emit('output', {'data': f"Erreur lors du lancement: {str(e)}\n", 'type': 'stderr'})
        emit('execution_finished', {'code': 1})

@socketio.on('input_data')
def handle_input_data(data):
    sid = request.sid
    input_text = data.get('input', '') + '\n'
    if sid in running_processes:
        info = running_processes[sid]
        proc = info['proc']
        if proc.poll() is None:
            try:
                proc.stdin.write(input_text.encode('utf-8'))
                proc.stdin.flush()
            except Exception as e:
                emit('output', {'data': f"\n[Erreur d'entrée: {str(e)}]\n", 'type': 'stderr'})

@socketio.on('stop_execution')
def handle_stop_execution():
    sid = request.sid
    if sid in running_processes:
        info = running_processes[sid]
        proc = info['proc']
        try:
            proc.kill()
        except Exception:
            pass
        emit('output', {'data': "\n[Processus interrompu par l'utilisateur.]\n", 'type': 'stderr'})

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
