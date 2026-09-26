import os
import sys
import subprocess
import io
from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-secret-key-render'

# Support de SQLite en local et PostgreSQL sur Render
db_url = os.environ.get('DATABASE_URL', 'sqlite:///editor.db')
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url

db = SQLAlchemy(app)

class SavedScript(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    scripts = SavedScript.query.all()
    return render_template('index.html', scripts=scripts)

@app.route('/run', methods=['POST'])
def run_code():
    data = request.json or {}
    code = data.get('code', '')
    try:
        result = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True,
            text=True,
            timeout=10
        )
        return jsonify({
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode
        })
    except subprocess.TimeoutExpired:
        return jsonify({'stderr': 'Erreur : Temps d exécution limite dépassé (10s max).', 'stdout': '', 'returncode': -1})
    except Exception as e:
        return jsonify({'stderr': str(e), 'stdout': '', 'returncode': -1})

@app.route('/install', methods=['POST'])
def install_library():
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

@app.route('/save', methods=['POST'])
def save_script():
    data = request.json or {}
    filename = data.get('filename', 'script.py')
    content = data.get('code', '')
    
    script = SavedScript.query.filter_by(filename=filename).first()
    if script:
        script.content = content
    else:
        script = SavedScript(filename=filename, content=content)
        db.session.add(script)
    
    db.session.commit()
    return jsonify({'status': 'Succès', 'id': script.id})

@app.route('/load/<int:script_id>')
def load_script(script_id):
    script = SavedScript.query.get_or_404(script_id)
    return jsonify({'filename': script.filename, 'content': script.content})

@app.route('/export', methods=['POST'])
def export_file():
    filename = request.form.get('filename', 'script.py')
    code = request.form.get('code', '')
    buffer = io.BytesIO()
    buffer.write(code.encode('utf-8'))
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='text/x-python')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
