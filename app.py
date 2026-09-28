import os
import sys
import subprocess
import tempfile
import shutil
import ast
import json
import uuid
import time
import re
import threading
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-studio-v6'

# Base de données SQLite local / PostgreSQL sur Render
db_url = os.environ.get('DATABASE_URL', 'sqlite:///editor.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

db = SQLAlchemy(app)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    files_json = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()

# Maintien des processus interactifs
running_processes = {}

def cleanup_old_processes():
    now = time.time()
    to_delete = []
    for pid, info in running_processes.items():
        if now - info.get('created_at', now) > 300: # Timeout de sécurité : 5 min
            try:
                info['proc'].kill()
            except Exception:
                pass
            shutil.rmtree(info.get('temp_dir', ''), ignore_errors=True)
            to_delete.append(pid)
    for pid in to_delete:
        del running_processes[pid]

@app.route('/')
def index():
    cleanup_old_processes()
    projects = Project.query.all()
    return render_template('index.html', projects=projects)

@app.route('/api/start', methods=['POST'])
def start_execution():
    cleanup_old_processes()
    data = request.json or {}
    files = data.get('files', {})
    entrypoint = data.get('entrypoint', 'main.py')

    if not files or entrypoint not in files:
        return jsonify({'error': f"Le fichier '{entrypoint}' est introuvable."}), 400

    process_id = str(uuid.uuid4())
    temp_dir = tempfile.mkdtemp(prefix="py_exec_")

    # Écriture de tous les fichiers du projet dans le dossier temporaire
    for fname, content in files.items():
        fpath = os.path.join(temp_dir, fname)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(content)

    exec_path = os.path.join(temp_dir, entrypoint)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        proc = subprocess.Popen(
            [sys.executable, '-u', exec_path],
            cwd=temp_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            env=env
        )

        proc_info = {
            'proc': proc,
            'temp_dir': temp_dir,
            'output': [],
            'status': 'running',
            'returncode': None,
            'created_at': time.time()
        }
        running_processes[process_id] = proc_info

        def read_output():
            while True:
                chunk = proc.stdout.read(1)
                if chunk == b'' and proc.poll() is not None:
                    break
                if chunk:
                    text = chunk.decode('utf-8', errors='replace')
                    proc_info['output'].append(text)
            
            proc_info['returncode'] = proc.wait()
            proc_info['status'] = 'finished'
            shutil.rmtree(temp_dir, ignore_errors=True)

        thread = threading.Thread(target=read_output)
        thread.daemon = True
        thread.start()

        return jsonify({'process_id': process_id})

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/poll/<process_id>', methods=['GET'])
def poll_execution(process_id):
    if process_id not in running_processes:
        return jsonify({'status': 'not_found'}), 404

    info = running_processes[process_id]
    chunks = "".join(info['output'])
    info['output'].clear()

    error_line = None
    error_msg = None
    if info['status'] == 'finished' and info['returncode'] != 0:
        match = re.search(r'File ".*?", line (\d+)(?:, in .*)?\n\s*(.*(?:\n\s*.*)?)', chunks)
        if match:
            error_line = int(match.group(1))
            error_msg = match.group(2).strip()

    return jsonify({
        'output': chunks,
        'status': info['status'],
        'returncode': info['returncode'],
        'error_line': error_line,
        'error_msg': error_msg
    })

@app.route('/api/input/<process_id>', methods=['POST'])
def send_input(process_id):
    if process_id not in running_processes:
        return jsonify({'error': 'Processus non trouvé.'}), 404

    data = request.json or {}
    user_input = data.get('input', '') + '\n'
    info = running_processes[process_id]

    if info['status'] == 'running' and info['proc'].poll() is None:
        try:
            info['proc'].stdin.write(user_input.encode('utf-8'))
            info['proc'].stdin.flush()
            # On affiche l'entrée utilisateur dans la console de sortie
            info['output'].append(user_input)
            return jsonify({'status': 'sent'})
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'status': 'process_already_stopped'})

@app.route('/api/stop/<process_id>', methods=['POST'])
def stop_execution(process_id):
    if process_id in running_processes:
        info = running_processes[process_id]
        try:
            info['proc'].kill()
        except Exception:
            pass
        info['status'] = 'stopped'
        shutil.rmtree(info['temp_dir'], ignore_errors=True)
        return jsonify({'status': 'stopped'})
    return jsonify({'status': 'not_found'})

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
            'msg': e.msg
        })
    except Exception as e:
        return jsonify({'valid': False, 'line': 1, 'column': 1, 'msg': str(e)})

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
    
    project = Project.query.filter_by(name=name).first()
    if project:
        project.files_json = json.dumps(files)
    else:
        project = Project(name=name, files_json=json.dumps(files))
        db.session.add(project)
    
    db.session.commit()
    return jsonify({'status': 'success', 'id': project.id})

@app.route('/load_project/<int:project_id>')
def load_project(project_id):
    project = Project.query.get_or_404(project_id)
    return jsonify({'name': project.name, 'files': json.loads(project.files_json)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
