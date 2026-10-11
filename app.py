import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash #Flask lo mete en una cookie firmada con tu SECRET_KEY
from flask import Flask, jsonify, request, render_template, redirect, url_for, flash, session, abort,g
from functools import wraps
from datetime import datetime, timedelta
import db
from db import get_db
from abc import ABC, abstractmethod
DURACION_HORAS = 2          # cuánto dura una reserva

# Configuración mínima
app = Flask(__name__)

# Cookie más segura
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,     # el JS no puede leer la cookie
    SESSION_COOKIE_SAMESITE='Lax',    # frena envíos desde otros sitios
    # SESSION_COOKIE_SECURE=True,     # actívalo cuando uses HTTPS
)
# ---------- Cargar al usuario en CADA peticion con g ----------
@app.before_request
def cargar_usuario():
    """Si hay sesión, trae los datos del usuario desde la BD y los deja en g.usuario."""
    uid = session.get('usuario_id')
    if uid is None:
        g.usuario = None
    else:
        g.usuario = get_db().execute(
            "SELECT id, nombre, email, rol FROM usuario WHERE id = ?", (uid,)
        ).fetchone()                  # sin password: no la necesitas aquí





app.config['SECRET_KEY'] = 'clave-solo-para-desarrollo'
app.config['DATABASE'] = os.path.join(app.instance_path, 'restaurante.db')

os.makedirs(app.instance_path, exist_ok=True)
db.init_app(app)
#-----------FUNCIONES CON QUERIES DE BASE DE DATOS----------
def guardar_usuario(usuario):
    """Recibe un objeto Usuario (el que arma el Builder) y lo inserta en la BD."""
    conexion = get_db()
    conexion.execute(
        "INSERT INTO usuario (nombre, email, password, rol) VALUES (?, ?, ?, ?)",
        (usuario.nombre, usuario.email, usuario.password, usuario.rol)
    )
    conexion.commit()          # sin commit, el INSERT no se guarda


#-----------CLASES Y OBJETOS--------------------------------
#PATRO FACADE----------------------------------------------- (USADO EN client_confirmar)
class ReservaError(Exception):
    """Error de negocio con mensaje para el usuario y código HTTP."""
    def __init__(self, mensaje, codigo=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


# ---------- SUBSISTEMAS (cada uno hace una sola cosa) ----------
class MesaRepo:
    def __init__(self, db): self.db = db

    def validar(self, mesa_id, personas):
        mesa = self.db.execute("SELECT capacidad FROM mesa WHERE id = ?", (mesa_id,)).fetchone()
        if mesa is None:
            raise ReservaError("Esa mesa no existe.", 404)
        if personas > mesa['capacidad']:
            raise ReservaError(f"Esa mesa es para {mesa['capacidad']} personas como máximo.")


class Disponibilidad:
    def __init__(self, db): self.db = db

    def verificar(self, mesa_id, fecha, h_ini, h_fin):
        choque = self.db.execute(
            """SELECT 1 FROM reserva
               WHERE mesa_id = ? AND fecha = ? AND estado != 'cancelada'
                 AND hora_inicio < ? AND hora_fin > ?""",
            (mesa_id, fecha, h_fin, h_ini)
        ).fetchone()
        if choque:
            raise ReservaError("Esa mesa ya está reservada en ese horario.", 409)


class Catalogo:
    def __init__(self, db): self.db = db

    def lineas(self, pedido):
        """{plato_id: cantidad} → [(plato_id, cantidad, precio)] con el precio de la BD."""
        lineas = []
        for plato_id, cantidad in pedido.items():
            pl = self.db.execute(
                "SELECT id, precio FROM plato WHERE id = ? AND disponible = 1", (plato_id,)
            ).fetchone()
            if pl is None:
                raise ReservaError("Uno de los platos ya no está disponible.")
            lineas.append((pl['id'], cantidad, pl['precio']))
        return lineas


class CuentaRepo:
    def __init__(self, db): self.db = db

    def crear(self, mesa_id, fecha, h_ini, reserva_id, lineas):
        total = sum(c * p for _, c, p in lineas)
        cur = self.db.execute(
            """INSERT INTO cuenta (mesa_id, fecha_apertura, hora_apertura, estado, total, reserva_id)
               VALUES (?, ?, ?, 'reservada', ?, ?)""",
            (mesa_id, fecha, h_ini, total, reserva_id))
        cuenta_id = cur.lastrowid
        self.db.executemany(
            """INSERT INTO detalle_cuenta (cuenta_id, plato_id, cantidad, precio_unitario, subtotal)
               VALUES (?, ?, ?, ?, ?)""",
            [(cuenta_id, pid, c, p, c * p) for pid, c, p in lineas])


# ---------- LA FACHADA ----------
class ReservaFacade:
    """Una sola llamada que coordina todos los subsistemas."""

    def __init__(self, db):
        self.db = db
        self.mesas = MesaRepo(db)
        self.disponibilidad = Disponibilidad(db)
        self.catalogo = Catalogo(db)
        self.cuentas = CuentaRepo(db)

    def reservar(self, usuario_id, mesa_id, personas, inicio, pedido):
        fin = inicio + timedelta(hours=DURACION_HORAS)
        fecha = inicio.strftime("%Y-%m-%d")
        h_ini, h_fin = inicio.strftime("%H:%M"), fin.strftime("%H:%M")

        try:
            self.db.execute("BEGIN IMMEDIATE")            # evita reservas simultáneas
            self.mesas.validar(mesa_id, personas)
            self.disponibilidad.verificar(mesa_id, fecha, h_ini, h_fin)
            lineas = self.catalogo.lineas(pedido)

            cur = self.db.execute(
                """INSERT INTO reserva (usuario_id, mesa_id, fecha, hora_inicio, hora_fin, cantidad_personas)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (usuario_id, mesa_id, fecha, h_ini, h_fin, personas))
            reserva_id = cur.lastrowid
            if lineas:
                self.cuentas.crear(mesa_id, fecha, h_ini, reserva_id, lineas)

            self.db.commit()
            return reserva_id

        except ReservaError:
            self.db.rollback()
            raise                                          # el mensaje ya viene listo
        except sqlite3.Error:
            self.db.rollback()
            raise ReservaError("No se pudo guardar la reserva.", 500)
#PATRON DECORATOR--------------------------------------------
class Cobro(ABC):
    """Interfaz común que comparten la cuenta base y todos los decoradores."""
    @abstractmethod
    def subtotal(self): ...
    @abstractmethod
    def total(self): ...
    @abstractmethod
    def desglose(self): ...          # lista de (concepto, valor) para mostrar


class CuentaBase(Cobro):             # el componente concreto
    def __init__(self, lineas):      # lineas: [(nombre, cantidad, precio_unitario)]
        self.lineas = lineas

    def subtotal(self): return sum(c * p for _, c, p in self.lineas)
    def total(self):    return self.subtotal()
    def desglose(self): return [("Subtotal", self.subtotal())]


class CobroDecorator(Cobro):         # el decorador base: envuelve y delega
    def __init__(self, interno):
        self._interno = interno

    def subtotal(self): return self._interno.subtotal()
    def total(self):    return self._interno.total() + self._extra()
    def desglose(self): return self._interno.desglose() + [(self._concepto(), self._extra())]

    @abstractmethod
    def _extra(self): ...            # cuánto suma (o resta) este decorador
    @abstractmethod
    def _concepto(self): ...


class _Porcentaje(CobroDecorator):
    nombre, signo = "", 1
    def __init__(self, interno, tasa):
        super().__init__(interno)
        self.tasa = tasa
    def _extra(self):    return self.signo * round(self.subtotal() * self.tasa)
    def _concepto(self): return f"{self.nombre} ({self.tasa:.0%})"


class ConImpuesto(_Porcentaje): nombre = "Impuesto al consumo"
class ConPropina(_Porcentaje):  nombre = "Propina sugerida"
class ConDescuento(_Porcentaje): nombre, signo = "Descuento", -1

        
#-----------PATRON BUILDER----------------------------------
class Usuario:

    def __init__(self, nombre, email, password, rol):
        self.nombre = nombre
        self.email = email
        self.password = password
        self.rol = rol

    # Clase interna Builder
    class Builder:

        def __init__(self):
            self.nombre = ""
            self.email = ""
            self.password = ""
            self.rol = "cliente"   # por defecto es cliente, igual que en la base de datos

        def set_nombre(self, nombre):
            self.nombre = nombre
            return self

        def set_email(self, email):
            self.email = email
            return self

        def set_password(self, password):
            self.password = password
            return self

        def set_rol(self, rol):
            self.rol = rol
            return self

        def build(self):
            return Usuario(
                self.nombre,
                self.email,
                self.password,
                self.rol
            )

#Patron factory-----------------------------------------------


class FactoryUsuario:
    @staticmethod
    def crear_usuario(rol, **datos):
        if rol == "admin":
            return Usuario(
                nombre=datos.get("nombre", ""),
                email=datos.get("email", ""),
                password=datos.get("password", ""),
                rol="admin"
            )
        elif rol == "cliente":
            return Usuario(
                nombre=datos.get("nombre", ""),
                email=datos.get("email", ""),
                password=datos.get("password", ""),
                rol="cliente"
            )
        else:
            raise ValueError(f"Rol no válido: {rol}")





#------------Funciones de login required y admin required
def login_required(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):

        if session.get('rol') == 'admin':
            return redirect(url_for('index'))

        if 'usuario_id' not in session:

            return redirect(url_for('index'))
        return vista(*args, **kwargs)
    return envoltura

def admin_required(vista):
    @wraps(vista)
    def envoltura(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('index'))
        if session.get('rol') != 'admin':
            abort(403)          # "prohibido": estás logueado pero no tienes permiso
        return vista(*args, **kwargs)
    return envoltura

#----- CERRAR SESION---

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada.')
    return redirect(url_for('index'))
#--------------------------------------------------------


# PRIMER ENDPOINT: consulta simple a la base de datos
@app.route('/')
def index():
    return render_template("index.html")


# RUTA DEL ADMIN-------------------------------------------------------------------------
@app.route('/loginadmin', methods=["POST"])
def loginadmin():
    return render_template("adminlogin.html")#HTML CON EL FORMULARIO DEL ADMIN

@app.route('/initadmin', methods=["POST"])
def initadmin():

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    fila = get_db().execute(
        "SELECT id, password, rol FROM usuario WHERE email = ?", (email,)
    ).fetchone()

    # Mensaje genérico: no revela si el correo existe o si falló la contraseña
    if fila is None or fila['rol'] != 'admin' or not check_password_hash(fila['password'], password):
        return jsonify(mensaje="Correo o contraseña incorrectos.")

    session.clear()                       # descarta cualquier sesión anterior
    session['usuario_id'] = fila['id']    # ← lo único que se guarda
    session['rol'] = fila['rol']
    return redirect(url_for('admin_menu'))

@app.route('/admin/menu')                  # GET por defecto
@admin_required
def admin_menu():
    return render_template("admin_menu.html")

@app.route('/admin/menu/verclientes')                  # GET por defecto
@admin_required
def admin_verclientes():
    filas = get_db().execute("""
        SELECT
           id ,nombre, email, rol FROM usuario WHERE rol = 'cliente'
    """, ).fetchall()
    return jsonify([dict(f) for f in filas])

@app.route('/admin/menu/eliminarcliente', methods=['DELETE'])
@admin_required
def admin_eliminar_cliente():
    datos = request.get_json()
    cliente_id = datos.get('id') if datos else None

    if cliente_id is None:
        return jsonify(
            ok=False,
            mensaje="Falta el ID del cliente"
        ), 400

    db = get_db()

    cliente = db.execute(
        "SELECT id FROM usuario WHERE id = ? AND rol = ?",
        (cliente_id, "cliente")
    ).fetchone()

    if cliente is None:
        return jsonify(
            ok=False,
            mensaje="Cliente no encontrado"
        ), 404

    try:
        # 1. Obtener las cuentas asociadas a las reservas del cliente
        cuentas = db.execute(
            """
            SELECT c.id
            FROM cuenta AS c
            INNER JOIN reserva AS r
                ON c.reserva_id = r.id
            WHERE r.usuario_id = ?
            """,
            (cliente_id,)
        ).fetchall()

        # 2. Eliminar los detalles de cada cuenta
        for cuenta in cuentas:
            db.execute(
                "DELETE FROM detalle_cuenta WHERE cuenta_id = ?",
                (cuenta['id'],)
            )

        # 3. Eliminar las cuentas del cliente
        db.execute(
            """
            DELETE FROM cuenta
            WHERE reserva_id IN (
                SELECT id
                FROM reserva
                WHERE usuario_id = ?
            )
            """,
            (cliente_id,)
        )

        # 4. Eliminar las reservas del cliente
        db.execute(
            "DELETE FROM reserva WHERE usuario_id = ?",
            (cliente_id,)
        )

        # 5. Finalmente, eliminar al usuario
        db.execute(
            "DELETE FROM usuario WHERE id = ? AND rol = ?",
            (cliente_id, "cliente")
        )

        db.commit()

        return jsonify(
            ok=True,
            mensaje="Cliente, reservas y cuentas eliminados correctamente"
        )

    except Exception:
        db.rollback()
        app.logger.exception("Error al eliminar el cliente")
        return jsonify(
            ok=False,
            mensaje="No se pudo eliminar el cliente por registros relacionados."
        ), 500




@app.route('/admin/menu/verreservas')                  # GET por defecto
@admin_required
def admin_verreservas1():
    filas = get_db().execute("""
        SELECT
            r.id AS reserva_id,
            u.id AS usuario_id,
            u.nombre AS nombre_usuario,
            m.id AS mesa_id,
            m.numero AS numero_mesa,
            m.capacidad AS capacidad_mesa,
            r.cantidad_personas,
            r.fecha,
            r.hora_inicio,
            r.hora_fin,
            r.estado
        FROM reserva AS r
        INNER JOIN usuario AS u ON r.usuario_id = u.id
        INNER JOIN mesa AS m ON r.mesa_id = m.id
        ORDER BY r.fecha, r.hora_inicio
    """, ).fetchall()
    return jsonify([dict(f) for f in filas])

@app.route('/admin/menu/veradmins')                  # GET por defecto
@admin_required
def admin_veradmins():
    filas = get_db().execute("""
        SELECT id, nombre, email, rol
        FROM usuario
        WHERE rol = 'admin'
          AND id != ?
          AND email != ?
    """, (
        session['usuario_id'],
        'juandavidlopezyara65@gmail.com'
    )).fetchall()
    return jsonify([dict(f) for f in filas])




@app.route('/admin/menu/eliminaradmin', methods=['DELETE'])                  # GET por defecto
@admin_required
def admin_eliminaradmins():
    datos = request.get_json()
    admin_id = datos.get('id') if datos else None

    if admin_id is None:
        return jsonify(
            ok=False,
            mensaje="Falta el ID del cliente"
        ), 400

    db = get_db()

    # 5. Finalmente, eliminar al usuario
    db.execute(
            "DELETE FROM usuario WHERE id = ? AND rol = ?",
            (admin_id, "admin")
        )
    db.commit()

    return jsonify(
            ok=True,
            mensaje="Admin eliminado"
        ), 200



@app.route('/admin/menu/vercuentas')
@admin_required
def admin_cuentas():
    filas = get_db().execute("""
        SELECT
            c.id AS cuenta_id,
            u.nombre AS nombre_usuario,
            u.email AS email_usuario,
            m.numero AS numero_mesa,
            c.fecha_apertura,
            c.hora_apertura,
            c.total
        FROM cuenta AS c
        INNER JOIN reserva AS r
            ON c.reserva_id = r.id
        INNER JOIN usuario AS u
            ON r.usuario_id = u.id
        INNER JOIN mesa AS m
            ON c.mesa_id = m.id
        ORDER BY c.fecha_apertura DESC, c.hora_apertura DESC
    """).fetchall()

    return jsonify([dict(f) for f in filas])

@app.route('/admin/menu/liquidarcuenta', methods=['DELETE'])
@admin_required
def admin_liquidar_cuenta():
    datos = request.get_json()
    cuenta_id = datos.get('id') if datos else None

    if cuenta_id is None:
        return jsonify(
            ok=False,
            mensaje="Falta el ID de la cuenta"
        ), 400

    db = get_db()

    # Obtener la reserva asociada a esta cuenta exacta
    reserva = db.execute(
        "SELECT reserva_id FROM cuenta WHERE id = ?",
        (cuenta_id,)
    ).fetchone()

    # 1. Eliminar los detalles de la cuenta
    db.execute(
        "DELETE FROM detalle_cuenta WHERE cuenta_id = ?",
        (cuenta_id,)
    )

    # 2. Eliminar la cuenta
    db.execute(
        "DELETE FROM cuenta WHERE id = ?",
        (cuenta_id,)
    )

    # 3. Eliminar la reserva asociada a esa cuenta
    if reserva and reserva['reserva_id'] is not None:
        db.execute(
            "DELETE FROM reserva WHERE id = ?",
            (reserva['reserva_id'],)
        )

    db.commit()

    return jsonify(
        ok=True,
        mensaje="Cuenta y reserva eliminadas correctamente"
    ), 200







@app.route('/admin/menu/registrar')                  # GET por defecto
@admin_required
def admin_registrar():
    return render_template("admin_registrar.html")


@app.route('/admin/menu/registrar/registrado', methods=["POST"])
@admin_required
def admin_registrado():

    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    rol = request.form.get("rol", "").strip().lower()

    usuario = FactoryUsuario.crear_usuario(
        rol=rol,
        nombre=nombre,
        email=email,
        password=generate_password_hash(password)
    )

    try:
        guardar_usuario(usuario)

    except sqlite3.IntegrityError as e:
        print("Error de integridad:", e)
        return jsonify(
            ok=False,
            mensaje="No se pudo registrar el usuario. Revisa los datos."
        ), 400

    return redirect(url_for("admin_menu"))





#RUTA DEL ADMIN---------------------------------------------------------------------------
#RUTA DEL CLIENTE-------------------------------------------------------------------------
@app.route('/loginclient', methods=["POST"])
def loginclient():
    return render_template("clientlogin.html")#HTML CON EL FORMULARIO DEL ADMIN

@app.route('/initclient', methods=["POST"])
def initclient():
    
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    fila = get_db().execute(
        "SELECT id, password, rol FROM usuario WHERE email = ?", (email,)
    ).fetchone()

    # Mensaje genérico: no revela si el correo existe o si falló la contraseña
    if fila is None or not check_password_hash(fila['password'], password):
        return jsonify(mensaje="Correo o contraseña incorrectos.")

    session.clear()                       # descarta cualquier sesión anterior
    session['usuario_id'] = fila['id']    # ← lo único que se guarda
    session['rol'] = fila['rol']
    return redirect(url_for('client_menu'))

@app.route('/client/menu')                  # GET por defecto
@login_required
def client_menu():
    return render_template("client_menu.html")   

@app.route('/client/menu/verreservas')                
@login_required
def client_reservado():

    uid = session.get('usuario_id')

    if uid is None:
        return jsonify(ok=False, mensaje="Debes iniciar sesión."), 401

    filas = get_db().execute("""
        SELECT
            r.id AS reserva_id,
            u.id AS usuario_id,
            u.nombre AS nombre_usuario,
            m.id AS mesa_id,
            m.numero AS numero_mesa,
            m.capacidad AS capacidad_mesa,
            r.cantidad_personas,
            r.fecha,
            r.hora_inicio,
            r.hora_fin,
            r.estado
        FROM reserva AS r
        INNER JOIN usuario AS u ON r.usuario_id = u.id
        INNER JOIN mesa AS m ON r.mesa_id = m.id
        WHERE r.usuario_id = ?
        ORDER BY r.fecha, r.hora_inicio
    """, (uid,)).fetchall()
    return jsonify([dict(f) for f in filas])

@app.route('/client/menu/vercuentas')                
@login_required
def client_cuentas():

    uid = session.get('usuario_id')

    if uid is None:
        return jsonify(ok=False, mensaje="Debes iniciar sesión."), 401

    filas = get_db().execute(
    """
    SELECT
        m.numero AS numero_mesa,
        c.fecha_apertura,
        c.hora_apertura,
        c.total
    FROM reserva AS r
    INNER JOIN cuenta AS c
        ON c.reserva_id = r.id
    INNER JOIN mesa AS m
        ON c.mesa_id = m.id
    WHERE r.usuario_id = ?
    ORDER BY c.fecha_apertura, c.hora_apertura;
    """, (uid,)).fetchall()
    return jsonify([dict(f) for f in filas])



@app.route('/client/menu/reservar')                
@login_required
def client_reservar():
    filas = get_db().execute(
        "SELECT id, numero, capacidad FROM mesa ORDER BY numero"
    ).fetchall()
    return jsonify([dict(f) for f in filas])
 
@app.route('/client/menu/platos')
@login_required
def client_platos():
    filas = get_db().execute(
        """SELECT id, nombre, descripcion, precio, imagen
           FROM plato
           WHERE disponible = 1
           ORDER BY categoria_id, nombre"""
    ).fetchall()

    platos = []
    for f in filas:
        p = dict(f)
        # url_for codifica espacios y tildes: "Bruschetta Clásica.png" → "Bruschetta%20Cl%C3%A1sica.png"
        p['imagen_url'] = (
            url_for('static', filename='img/platos/' + p['imagen']) if p['imagen'] else None
        )
        platos.append(p)
    return jsonify(platos)


@app.route('/client/reservar/confirmar', methods=["POST"])
@login_required
def client_confirmar():
    datos = request.get_json(silent=True) or {}

    # ---- 1. Validar lo que llega (el navegador no es de fiar) ----
    if not isinstance(datos, dict):
        return jsonify(ok=False, mensaje="La petición no llegó como JSON."), 400

    try:
        mesa_id = int(datos.get("mesa_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, mensaje="Mesa inválida: vuelve a elegirla."), 400

    try:
        personas = int(datos.get("personas"))
    except (TypeError, ValueError):
        return jsonify(ok=False, mensaje="Número de personas inválido."), 400

    try:
        inicio = datetime.strptime(f"{datos.get('fecha')} {datos.get('hora')}", "%Y-%m-%d %H:%M")
    except ValueError:
        return jsonify(ok=False, mensaje="Fecha u hora inválidas."), 400

    try:
        pedido = {int(k): int(v) for k, v in (datos.get("platos") or {}).items()}
    except (TypeError, ValueError, AttributeError):
        return jsonify(ok=False, mensaje="El pedido de platos es inválido."), 400

    fin = inicio + timedelta(hours=DURACION_HORAS)
    if inicio < datetime.now():
        return jsonify(ok=False, mensaje="Esa fecha y hora ya pasaron."), 400
    if fin.date() != inicio.date():
        return jsonify(ok=False, mensaje="La reserva no puede pasar de medianoche."), 400
    if personas < 1:
        return jsonify(ok=False, mensaje="Indica cuántas personas son."), 400
    if any(not 1 <= c <= 20 for c in pedido.values()):
        return jsonify(ok=False, mensaje="Cantidad de platos inválida."), 400

    fecha, h_ini, h_fin = inicio.strftime("%Y-%m-%d"), inicio.strftime("%H:%M"), fin.strftime("%H:%M")
    db = get_db()

    def fallo(mensaje, codigo):
        db.rollback()
        return jsonify(ok=False, mensaje=mensaje), codigo

    try:
        # Bloquea las escrituras: evita que dos personas reserven la misma mesa a la vez
        db.execute("BEGIN IMMEDIATE")

        # ---- 2. La mesa existe y le caben las personas ----
        mesa = db.execute("SELECT capacidad FROM mesa WHERE id = ?", (mesa_id,)).fetchone()
        if mesa is None:
            return fallo("Esa mesa no existe.", 404)
        if personas > mesa['capacidad']:
            return fallo(f"Esa mesa es para {mesa['capacidad']} personas como máximo.", 400)

        # ---- 3. No se cruza con otra reserva (dos rangos se cruzan si cada uno empieza antes de que el otro termine) ----
        choque = db.execute(
            """SELECT 1 FROM reserva
               WHERE mesa_id = ? AND fecha = ? AND estado != 'cancelada'
                 AND hora_inicio < ? AND hora_fin > ?""",
            (mesa_id, fecha, h_fin, h_ini)
        ).fetchone()
        if choque:
            return fallo("Esa mesa ya está reservada en ese horario.", 409)

        # ---- 4. Los platos: el PRECIO sale de la base de datos, no del navegador ----
        lineas = []
        for plato_id, cantidad in pedido.items():
            pl = db.execute(
                "SELECT id, precio FROM plato WHERE id = ? AND disponible = 1", (plato_id,)
            ).fetchone()
            if pl is None:
                return fallo("Uno de los platos ya no está disponible.", 400)
            lineas.append((pl['id'], cantidad, pl['precio']))

        # ---- 5. Guardar: reserva → cuenta → detalle ----
        cur = db.execute(
            """INSERT INTO reserva (usuario_id, mesa_id, fecha, hora_inicio, hora_fin, cantidad_personas)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session['usuario_id'], mesa_id, fecha, h_ini, h_fin, personas)   # el usuario sale de la sesión
        )
        reserva_id = cur.lastrowid

        if lineas:                                   # sin platos: solo se reserva la mesa
            total = sum(c * p for _, c, p in lineas)
            cur = db.execute(
                """INSERT INTO cuenta (mesa_id, fecha_apertura, hora_apertura, estado, total, reserva_id)
                   VALUES (?, ?, ?, 'reservada', ?, ?)""",
                (mesa_id, fecha, h_ini, total, reserva_id)
            )
            cuenta_id = cur.lastrowid
            db.executemany(
                """INSERT INTO detalle_cuenta (cuenta_id, plato_id, cantidad, precio_unitario, subtotal)
                   VALUES (?, ?, ?, ?, ?)""",
                [(cuenta_id, pid, c, p, c * p) for pid, c, p in lineas]
            )

        db.commit()                                  # todo o nada

    except sqlite3.Error as e:
        app.logger.exception(e)
        return fallo("No se pudo guardar la reserva.", 500)

    return jsonify(ok=True, mensaje="¡Reserva confirmada!", reserva_id=reserva_id), 201


#RUTA DLE CLIENTE-------------------------------------------------------------------------



@app.route('/regisclient',methods=["POST"])
def formclient():
    return render_template("registrarcliente.html")
@app.route('/registro', methods=["POST"])
def regiscliente():
    nombre = request.form.get("nombre", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    cliente = (Usuario.Builder()
               .set_nombre(nombre)
               .set_email(email)
               .set_password(generate_password_hash(password))
               .build())

    try:
        guardar_usuario(cliente)
    except sqlite3.IntegrityError:
        return jsonify(ok=False, mensaje="Ese correo ya está registrado.")
    return redirect(url_for("index"))


if __name__ == '__main__':
    app.run(debug=True)