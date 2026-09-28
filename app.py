import os
import sys
import subprocess
import tempfile
import shutil
import ast
import json
import re
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-studio-v4'

# Support SQLite local & PostgreSQL sur Render
from flask_sqlalchemy import SQLAlchemy
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

@app.route('/')
def index():
    projects = Project.query.all()
    return render_template('index.html', projects=projects)

@app.route('/run', methods=['POST'])
def run_code():
    data = request.json or {}
    files = data.get('files', {})
    entrypoint = data.get('entrypoint', 'main.py')
    stdin_data = data.get('stdin', '')

    if not files or entrypoint not in files:
        return jsonify({
            'stdout': '',
            'stderr': f"Erreur: Le fichier d'entrée '{entrypoint}' est introuvable.",
            'returncode': 1
        })

    temp_dir = tempfile.mkdtemp(prefix="py_exec_")
    try:
        # Écriture de tous les fichiers du projet
        for fname, content in files.items():
            fpath = os.path.join(temp_dir, fname)
            os.makedirs(os.path.dirname(fpath), exist_ok=True)
            with open(fpath, 'w', encoding='utf-8') as f:
                f.write(content)

        exec_path = os.path.join(temp_dir, entrypoint)
        
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        # Exécution du sous-processus Python
        res = subprocess.run(
            [sys.executable, '-u', exec_path],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=12,
            cwd=temp_dir,
            env=env
        )

        stdout = res.stdout
        stderr = res.stderr
        returncode = res.returncode

        # Détection de la ligne d'erreur exacte dans le Traceback
        error_line = None
        error_msg = None
        if stderr:
            match = re.search(r'File ".*?", line (\d+)(?:, in .*)?\n\s*(.*(?:\n\s*.*)?)', stderr)
            if match:
                error_line = int(match.group(1))
                error_msg = match.group(2).strip()

        return jsonify({
            'stdout': stdout,
            'stderr': stderr,
            'returncode': returncode,
            'error_line': error_line,
            'error_msg': error_msg
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            'stdout': '',
            'stderr': "Erreur: Temps d'exécution dépassé (Limite fixée à 12 secondes).",
            'returncode': -1
        })
    except Exception as e:
        return jsonify({'stdout': '', 'stderr': str(e), 'returncode': -1})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

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
