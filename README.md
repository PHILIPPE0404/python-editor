# 🐍 Éditeur Python Web

Un éditeur de code Python léger et complet basé sur **Flask** et **Ace Editor**, prêt à être déployé gratuitement sur **Render**.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.0+-000000?style=for-the-badge&logo=flask&logoColor=white)
![Render](https://img.shields.io/badge/Render-Deployed-46E3B7?style=for-the-badge&logo=render&logoColor=white)

---

## ✨ Fonctionnalités

- ⚡ **Exécution en direct :** Exécution sécurisée de scripts Python via un sous-processus serveur (avec limite de temps de 10s).
- 🎨 **Éditeur moderne :** Éditeur Ace avec coloration syntaxique Python et thème sombre (Monokai).
- 📂 **Gestion des fichiers :** Importation de fichiers `.py` locaux et exportation directe du code.
- 💾 **Base de données intégrée :** Sauvegarde et chargement de scripts en base de données (SQLite en local, PostgreSQL en production).
- 📦 **Gestionnaire de paquets `pip` :** Installation dynamique de bibliothèques Python depuis l'interface web.

---

## 🛠️ Structure du Projet

python-editor/
├── app.py              # Application Flask principale (Routes & Logique)
├── requirements.txt    # Dépendances Python
├── Procfile            # Instructions de démarrage pour Render / Gunicorn
├── .gitignore          # Fichiers ignorés par Git
└── templates/
    └── index.html      # Interface utilisateur et éditeur Ace
    
## 🚀 Installation & Lancement en Local


1. Cloner le dépôt
Bash
git clone [https://github.com/votre-compte/python-editor.git](https://github.com/votre-compte/python-editor.git)
cd python-editor

2. Créer un environnement virtuel
Bash
python -m venv venv
# Sur Linux/macOS :
source venv/bin/activate
# Sur Windows :
venv\Scripts\activate

3. Installer les dépendances
Bash
pip install -r requirements.txt

4. Lancer l'application
Bash
python app.py
L'application sera accessible sur http://localhost:5000.

## ☁️ Déploiement sur Render

Push ton projet sur GitHub.
Rends-toi sur Render.com et crée un nouveau Web Service.
Connecte ton dépôt GitHub.
Renseigne les commandes suivantes :
Build Command : pip install -r requirements.txt
Start Command : gunicorn app:app
Clique sur Create Web Service.

## 🛡️ Sécurité & Limitations

Les exécutions de scripts ont un timeout par défaut fixé à 10 secondes pour éviter le blocage du serveur.
L'installation de modules via pip s'effectue directement dans l'environnement du serveur de déploiement
