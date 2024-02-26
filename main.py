from flask import Flask, jsonify, request
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
from flask_cors import CORS
from sshtunnel import SSHTunnelForwarder
import json
from datetime import datetime
import asyncio
import websockets

load_dotenv()

app = Flask(__name__)

CORS(app, resources={r"/*": {"origins": "*"}})

db_user = os.getenv('DB_USERNAME')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST')
db_port = os.getenv('DB_PORT')
db_name = os.getenv('DB_NAME')

use_ssh_tunnel = os.getenv('USE_SSH_TUNNEL', '').lower() in ['true', 'yes', '1']
print(use_ssh_tunnel)


def create_database_engine():
    if use_ssh_tunnel:
        ssh_host = os.getenv('SSH_HOST')
        ssh_port = int(os.getenv('SSH_PORT'))
        ssh_user = os.getenv('SSH_USER')
        ssh_password = os.getenv('SSH_PASSWORD')

        tunnel = SSHTunnelForwarder(
            (ssh_host, ssh_port),
            ssh_username=ssh_user,
            ssh_password=ssh_password,
            remote_bind_address=(db_host, int(db_port))
        )
        tunnel.start()
        db_uri = f'postgresql://{db_user}:{db_password}@localhost:{tunnel.local_bind_port}/{db_name}'
        print("Connexion à la base de données via tunnel SSH établie avec succès. Tunel")
    else:
        db_uri = f'postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}'
        print("Connexion directe à la base de données établie avec succès. Direct")
    engine = create_engine(db_uri)
    return engine, tunnel if use_ssh_tunnel else engine


def close_database_engine(engine, tunnel):
    if use_ssh_tunnel:
        tunnel.stop()
    else:
        engine.dispose()


def save_data_in_database(data):
    try:
        engine, tunnel = create_database_engine()

        Session = sessionmaker(bind=engine)
        session = Session()
        time = datetime.fromtimestamp(data.get('x') / 1000.0)
        session.execute(
            text("INSERT INTO sensors_rms (time, acc_0_rms, acc_1_rms) VALUES (:time, :acc_0_rms, :acc_1_rms)"),
            {
                'time': time,
                'acc_0_rms': data.get('y1', 0.0),
                'acc_1_rms': data.get('y2', 0.0)
            }
        )
        session.commit()
        return True
    except Exception as e:
        print(f"Erreur lors de l'enregistrement des données dans la base de données : {e}")
        return False
    finally:
        session.close()
        close_database_engine(engine, tunnel)


def get_data_from_database():
    try:
        engine, tunnel = create_database_engine()

        Session = sessionmaker(bind=engine)
        session = Session()
        result = session.execute(text("SELECT time, acc_0_rms, acc_1_rms FROM sensors_rms"))
        rows = [row for row in result]
        data = [{'time': row[0], 'acc_0_rms': row[1], 'acc_1_rms': row[2]} for row in rows]
        return data
    except Exception as e:
        print(f"Erreur lors de la récupération des données depuis la base de données : {e}")
        return []
    finally:
        session.close()
        close_database_engine(engine, tunnel)


@app.route('/')
def welcome():
    return 'Bienvenue sur service BDD'


@app.route('/view_data')
def view_data():
    data = get_data_from_database()
    return jsonify(data)


@app.route('/save_data_from_chart', methods=['POST'])
def save_data_from_chart():
    data = request.json
    if data and 'time' in data and 'acc_0_rms' in data and 'acc_1_rms' in data:
        success = save_data_in_database(data)
        if success:
            return jsonify({'success': True, 'message': "Données enregistrées avec succès"})
        else:
            return jsonify({'success': False, 'message': "Erreur lors de l'enregistrement des données"}), 500
    else:
        return jsonify({'success': False, 'message': "Données manquantes ou incorrectes"}), 400


json_file_path = 'data.json'


@app.route('/write_data_to_json', methods=['POST'])
def write_data_to_json():
    try:
        if os.path.exists(json_file_path):
            with open(json_file_path, 'a') as file:
                json_str = json.dumps(request.json)
                file.write(json_str + '\n')
        else:
            with open(json_file_path, 'w') as file:
                json_str = json.dumps(request.json)
                file.write(json_str + '\n')

        return jsonify({'success': True, 'message': 'Données enregistrées avec succès dans le fichier JSON'})
    except Exception as e:
        print("Erreur lors de l'écriture des données dans le fichier JSON :", e)
        return jsonify({'success': False, 'message': "Erreur lors de l'enregistrement des données dans le fichier "
                                                     "JSON : " + str(e)}), 500


@app.route('/save_data_to_database', methods=['POST'])
def save_data_to_database():
    try:
        data = request.json
        success = save_data_in_database(data)
        if success:
            return jsonify({'success': True, 'message': "Données enregistrées avec succès dans la base de données"})
        else:
            return jsonify(
                {'success': False,
                 'message': "Erreur lors de l'enregistrement des données dans la base de données"}), 500

    except Exception as e:
        return jsonify({'success': False, 'message': f"Erreur: {e}"}), 500


@app.route('/close_database_connection', methods=['POST'])
def close_database_connection():
    try:
        engine, tunnel = create_database_engine()
        close_database_engine(engine, tunnel)
        return jsonify({'success': True, 'message': "Connexion à la base de données fermée avec succès"})
    except Exception as e:
        return jsonify({'success': False,
                        'message': f"Erreur lors de la fermeture de la connexion à la base de données : {e}"}), 500



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5016)  # Exécutez l'API Flask sur le port 5016

# if __name__ == '__main__':
#     app.run(debug=True)
