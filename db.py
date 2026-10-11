import sqlite3
import click
from flask import current_app, g

#ARCHIVO DE CONEXION DE BASE DE DATOS CON FLASK

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(current_app.config['DATABASE'])
        g.db.row_factory = sqlite3.Row          # acceder a columnas por nombre
        g.db.execute('PRAGMA foreign_keys = ON')  # SQLite lo trae apagado por defecto, prende ruso de llaves foraneas
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))

@click.command('init-db')
def init_db_command():
    """Crea las tablas desde schema.sql"""
    init_db()
    click.echo('Base de datos inicializada.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)