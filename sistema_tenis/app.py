from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import pymysql
import os
import re
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave_secreta_sistema_tenis_upvm')


def get_db_connection():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'root'),
        password=os.environ.get('DB_PASSWORD', '12345678'),
        database=os.environ.get('DB_NAME', 'sistema_tenis_db'),
        port=int(os.environ.get('DB_PORT', 3306)),
        cursorclass=pymysql.cursors.DictCursor
    )


def registrar_evento(ruta, descripcion):
    if 'usuario_id' in session:
        try:
            conexion = get_db_connection()
            cursor = conexion.cursor()
            cursor.execute(
                "INSERT INTO metricas (usuario_id, ruta, evento) VALUES (%s, %s, %s)",
                (session['usuario_id'], ruta, descripcion)
            )
            conexion.commit()
            cursor.close()
            conexion.close()
        except Exception as e:
            print("Error al registrar evento:", e)


# ----------------------------------------------------
# AUTENTICACIÓN Y COOKIES
# ----------------------------------------------------
@app.route('/api/consentimiento-cookies', methods=['POST'])
def consentimiento_cookies():
    data = request.get_json(silent=True) or {}
    aceptadas = bool(data.get('aceptadas', False))
    session['cookies_aceptadas'] = aceptadas

    if 'usuario_id' in session:
        detalle = 'Cookies aceptadas por el usuario' if aceptadas else 'Cookies no aceptadas'
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO eventos (usuario_id, evento, ruta) VALUES (%s, %s, %s)",
                (session['usuario_id'], detalle, '/login')
            )
            conn.commit()
        conn.close()

    resp = jsonify({'ok': True, 'cookies_aceptadas': aceptadas})
    resp.set_cookie(
        'cookies_upvm',
        'aceptadas' if aceptadas else 'pendiente',
        max_age=60 * 60 * 24 * 30,
        path='/'
    )
    return resp


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        correo = request.form['correo']
        password = request.form['password']

        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM usuarios WHERE correo = %s", (correo,))
            user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password_hash'], password):
            session['usuario_id'] = user['id']
            session['nombre'] = user['nombre']
            session['rol'] = user['rol']

            acepto_cookies = (
                request.form.get('cookies_aceptadas') == 'true'
                or request.cookies.get('cookies_upvm') == 'aceptadas'
                or session.get('cookies_aceptadas') is True
            )
            session['cookies_aceptadas'] = acepto_cookies
            estado_cookies = 'Cookies aceptadas' if acepto_cookies else 'Sin cookies aceptadas'

            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO eventos (usuario_id, evento, ruta) VALUES (%s, %s, %s)",
                    (user['id'], f"Inicio de sesión exitoso ({estado_cookies})", '/login')
                )
                conn.commit()
            conn.close()

            resp = redirect(url_for('index'))
            if acepto_cookies:
                resp.set_cookie('cookies_upvm', 'aceptadas', max_age=60 * 60 * 24 * 30, path='/')
            return resp
        else:
            error = 'Correo o contraseña incorrectos.'

    return render_template('login.html', error=error)


@app.route('/registro', methods=['GET', 'POST'])
def registro():
    error = None
    if request.method == 'POST':
        nombre = request.form['nombre']
        correo = request.form['correo']
        password = generate_password_hash(request.form['password'])
        rol = 'client'

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO usuarios (nombre, correo, rol, password_hash) VALUES (%s, %s, %s, %s)",
                    (nombre, correo, rol, password)
                )
                conn.commit()
            return redirect(url_for('login'))
        except pymysql.err.IntegrityError:
            error = 'El correo electrónico ya está registrado.'
        finally:
            conn.close()

    return render_template('registro.html', error=error)


@app.route('/logout')
def logout():
    session.clear()
    resp = redirect(url_for('login'))
    return resp


# ----------------------------------------------------
# RUTA PRINCIPAL UNIFICADA (CLIENTE Y ADMIN)
# ----------------------------------------------------
@app.route('/')
def index():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO eventos (usuario_id, evento, ruta) VALUES (%s, %s, %s)",
            (session['usuario_id'], 'Visita a página principal', '/')
        )
        cursor.execute("SELECT * FROM productos ORDER BY id DESC LIMIT 4")
        productos = cursor.fetchall()
        conn.commit()
    conn.close()

    return render_template(
        'index.html',
        nombre=session['nombre'],
        rol=session.get('rol'),
        productos=productos
    )


# ----------------------------------------------------
# RUTAS ADMINISTRADOR (PANELES Y REPORTES)
# ----------------------------------------------------
@app.route('/dashboard')
def dashboard():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as total_usuarios FROM usuarios")
        total_usuarios = cursor.fetchone()['total_usuarios']

        cursor.execute("SELECT COUNT(*) as total_productos FROM productos")
        total_productos = cursor.fetchone()['total_productos']

        cursor.execute("SELECT COUNT(*) as total_clics FROM eventos")
        total_clics = cursor.fetchone()['total_clics']

        cursor.execute("SELECT COUNT(DISTINCT usuario_id) as visitantes_unicos FROM eventos")
        visitantes_unicos = cursor.fetchone()['visitantes_unicos']

        cursor.execute("""
            SELECT COUNT(*) AS total_cookies_aceptadas
            FROM eventos
            WHERE evento LIKE '%Cookies aceptadas%'
        """)
        total_cookies_aceptadas = cursor.fetchone()['total_cookies_aceptadas']

        # Lista detallada de usuarios registrados y visitantes únicos
        cursor.execute("""
            SELECT 
                u.id,
                u.nombre,
                u.correo,
                u.rol,
                COUNT(e.id) AS total_eventos,
                MAX(CASE WHEN e.evento LIKE '%Cookies aceptadas%' THEN 1 ELSE 0 END) AS cookies_aceptadas,
                MAX(e.creado_en) AS ultima_actividad
            FROM usuarios u
            LEFT JOIN eventos e ON e.usuario_id = u.id
            GROUP BY u.id, u.nombre, u.correo, u.rol
            ORDER BY total_eventos DESC, u.id ASC
        """)
        lista_visitantes = cursor.fetchall()

        # Conteo por ruta / página para identificar la más vista y los clics totales
        cursor.execute("""
            SELECT ruta, COUNT(*) AS total_vistas
            FROM eventos
            GROUP BY ruta
            ORDER BY total_vistas DESC
        """)
        rutas_vistas = cursor.fetchall()

        # Actividad reciente con el nombre exacto del usuario/cliente
        cursor.execute("""
            SELECT 
                e.id,
                e.usuario_id,
                COALESCE(u.nombre, CONCAT('Usuario #', e.usuario_id)) AS nombre_usuario,
                u.rol,
                e.evento,
                e.ruta,
                e.creado_en
            FROM eventos e
            LEFT JOIN usuarios u ON e.usuario_id = u.id
            ORDER BY e.creado_en DESC
            LIMIT 30
        """)
        eventos = cursor.fetchall()
    conn.close()

    pagina_mas_vista = rutas_vistas[0]['ruta'] if rutas_vistas else 'Sin datos'
    vistas_pagina_top = rutas_vistas[0]['total_vistas'] if rutas_vistas else 0

    rutas_labels = [r['ruta'] for r in rutas_vistas]
    rutas_valores = [int(r['total_vistas']) for r in rutas_vistas]

    visitantes_serializables = []
    for v in lista_visitantes:
        visitantes_serializables.append({
            'id': v['id'],
            'nombre': v['nombre'],
            'correo': v['correo'],
            'rol': v['rol'],
            'total_eventos': int(v['total_eventos'] or 0),
            'cookies_aceptadas': bool(v.get('cookies_aceptadas')),
            'ultima_actividad': str(v['ultima_actividad']) if v['ultima_actividad'] else 'Sin actividad'
        })

    return render_template(
        'dashboard.html',
        total_usuarios=total_usuarios,
        total_productos=total_productos,
        total_clics=total_clics,
        visitantes_unicos=visitantes_unicos,
        total_cookies_aceptadas=total_cookies_aceptadas,
        pagina_mas_vista=pagina_mas_vista,
        vistas_pagina_top=vistas_pagina_top,
        rutas_labels=rutas_labels,
        rutas_valores=rutas_valores,
        lista_visitantes=visitantes_serializables,
        eventos=eventos,
        rol=session.get('rol')
    )


# ----------------------------------------------------
# RUTA DEL MENÚ DE ADMINISTRADOR
# ----------------------------------------------------
@app.route('/admin/menu')
def admin_menu():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))
    return render_template('admin_menu.html', nombre=session['nombre'])


@app.route('/admin/compras')
def admin_compras():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 
                c.id,
                u.id AS usuario_id,
                u.nombre AS usuario,
                p.nombre AS producto,
                p.imagen,
                c.talla,
                c.cantidad,
                c.precio_unitario,
                c.total,
                c.creado_en
            FROM compras c
            JOIN usuarios u ON c.usuario_id = u.id
            JOIN productos p ON c.producto_id = p.id
            ORDER BY c.creado_en DESC
        """)
        registros = cursor.fetchall()
    conn.close()

    compras_por_usuario = {}
    total_ventas = 0
    ganancia_total = 0.0

    for reg in registros:
        cantidad = int(reg['cantidad'])
        precio_unitario = float(reg['precio_unitario'])
        subtotal = float(reg['total'])
        nombre_prod = f"{reg['producto']} ({reg['talla']})" if reg.get('talla') else reg['producto']

        total_ventas += cantidad
        ganancia_total += subtotal

        uid = reg['usuario_id']
        if uid not in compras_por_usuario:
            compras_por_usuario[uid] = {
                'usuario': reg['usuario'],
                'compras': [],
                'total_usuario': 0.0
            }

        compras_por_usuario[uid]['compras'].append({
            'producto': nombre_prod,
            'cantidad': cantidad,
            'precio_unitario': precio_unitario,
            'subtotal': subtotal,
            'imagen': reg['imagen'] or '',
            'fecha_hora': reg['creado_en']
        })
        compras_por_usuario[uid]['total_usuario'] += subtotal

    return render_template(
        'admin_compras.html',
        usuarios_compras=list(compras_por_usuario.values()),
        total_ventas=total_ventas,
        ganancia_total=ganancia_total,
        rol=session.get('rol')
    )


@app.route('/admin/ubicaciones')
def admin_ubicaciones():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT 
                c.id,
                u.id AS usuario_id,
                u.nombre AS usuario,
                CONCAT(
                    'Compra: ', p.nombre,
                    CASE WHEN c.talla IS NOT NULL AND c.talla != '' THEN CONCAT(' (Talla: ', c.talla, ')') ELSE '' END,
                    ' (Cant: ', c.cantidad, ')'
                ) AS referencia,
                c.latitud,
                c.longitud,
                c.creado_en
            FROM compras c
            JOIN usuarios u ON c.usuario_id = u.id
            JOIN productos p ON c.producto_id = p.id
            ORDER BY c.creado_en DESC
        """)
        registros = cursor.fetchall()
    conn.close()

    clientes_mapa = {}
    for reg in registros:
        uid = reg['usuario_id']
        if uid not in clientes_mapa:
            clientes_mapa[uid] = {
                'usuario_id': uid,
                'usuario': reg['usuario'],
                'ubicaciones': []
            }

        try:
            lat_val = float(reg['latitud']) if reg['latitud'] is not None else None
        except (ValueError, TypeError):
            lat_val = None

        try:
            lng_val = float(reg['longitud']) if reg['longitud'] is not None else None
        except (ValueError, TypeError):
            lng_val = None

        clientes_mapa[uid]['ubicaciones'].append({
            'id': reg['id'],
            'referencia': reg['referencia'],
            'latitud': lat_val,
            'longitud': lng_val,
            'fecha': str(reg['creado_en']) if reg['creado_en'] is not None else ''
        })

    return render_template(
        'admin_ubicaciones.html',
        clientes_compras=list(clientes_mapa.values()),
        ubicaciones=registros,
        rol=session.get('rol')
    )


@app.route('/admin/chat')
def admin_chat():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM chat WHERE creado_en < NOW() - INTERVAL 2 HOUR")
        conn.commit()

        cursor.execute("""
            SELECT c.id, c.usuario_id, c.nombre_usuario, c.mensaje, c.creado_en
            FROM chat c
            ORDER BY c.creado_en ASC
        """)
        mensajes = cursor.fetchall()
    conn.close()

    return render_template(
        'admin_chat.html',
        mensajes=mensajes,
        usuario_actual=session.get('usuario_id'),
        nombre_actual=session.get('nombre'),
        rol=session.get('rol')
    )


@app.route('/admin/chat/eliminar/<int:mensaje_id>', methods=['POST'])
def eliminar_mensaje_chat(mensaje_id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM chat WHERE id = %s", (mensaje_id,))
        conn.commit()
    conn.close()

    return redirect(url_for('admin_chat'))


@app.route('/admin/encuestas')
def admin_encuestas():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT e.id, u.nombre as usuario, e.calificacion, e.atencion, e.comentarios, e.mejora, e.recomendacion, e.creado_en
            FROM encuestas e
            JOIN usuarios u ON e.usuario_id = u.id
            ORDER BY e.creado_en DESC
        """)
        respuestas = cursor.fetchall()
    conn.close()

    return render_template('admin_encuestas.html', respuestas=respuestas, rol=session.get('rol'))


# ----------------------------------------------------
# GESTIÓN EXCLUSIVA DE PRODUCTOS PARA EL ADMIN
# ----------------------------------------------------
@app.route('/admin/productos', methods=['GET', 'POST'])
def admin_productos():
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        precio = request.form['precio']
        talla = request.form['talla']
        stock = request.form['stock']
        imagen = request.form.get('imagen', '')

        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO productos (nombre, descripcion, precio, talla, stock, imagen) VALUES (%s, %s, %s, %s, %s, %s)",
                (nombre, descripcion, precio, talla, stock, imagen)
            )
            conn.commit()
        conn.close()
        return redirect(url_for('admin_productos'))

    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM productos ORDER BY id DESC")
        lista_productos = cursor.fetchall()
    conn.close()

    return render_template('admin_productos.html', productos=lista_productos, rol=session.get('rol'))


# ----------------------------------------------------
# PRODUCTOS, COMPRA Y MÓDULOS
# ----------------------------------------------------
@app.route('/productos')
def productos():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            "INSERT INTO eventos (usuario_id, evento, ruta) VALUES (%s, %s, %s)",
            (session['usuario_id'], 'Visita al catálogo de productos', '/productos')
        )
        conn.commit()

        cursor.execute("SELECT * FROM productos ORDER BY id DESC")
        lista_productos = cursor.fetchall()
    conn.close()

    return render_template('productos.html', productos=lista_productos, rol=session.get('rol'))


@app.route('/comprar/<int:producto_id>', methods=['GET', 'POST'])
def vista_comprar(producto_id):
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM productos WHERE id = %s", (producto_id,))
        producto = cursor.fetchone()
    conn.close()

    if not producto:
        return redirect(url_for('productos'))

    if request.method == 'POST':
        cantidad = int(request.form.get('cantidad', 1))
        talla = request.form.get('talla') or producto.get('talla')
        latitud = request.form.get('latitud')
        longitud = request.form.get('longitud')

        if cantidad < 1 or cantidad > producto['stock']:
            return render_template('comprar.html', producto=producto, nombre_usuario=session.get('nombre'), error="Stock insuficiente.")

        precio_unitario = float(producto['precio'])
        total = round(precio_unitario * cantidad, 2)
        lat_val = float(latitud) if latitud not in (None, '') else None
        lng_val = float(longitud) if longitud not in (None, '') else None

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("UPDATE productos SET stock = stock - %s WHERE id = %s", (cantidad, producto_id))

                cursor.execute(
                    """
                    INSERT INTO compras (usuario_id, producto_id, talla, cantidad, precio_unitario, total, latitud, longitud)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (session['usuario_id'], producto_id, talla, cantidad, precio_unitario, total, lat_val, lng_val)
                )

                if lat_val is not None and lng_val is not None:
                    cursor.execute(
                        "INSERT INTO ubicaciones (usuario_id, nombre, latitud, longitud, precision_m) VALUES (%s, %s, %s, %s, %s)",
                        (session['usuario_id'], f"Compra: {producto['nombre']} (Cant: {cantidad})", lat_val, lng_val, 10)
                    )

                cursor.execute(
                    "INSERT INTO eventos (usuario_id, evento, ruta) VALUES (%s, %s, %s)",
                    (session['usuario_id'], f"Compra realizada ({cantidad}x {producto['nombre']})", f"/comprar/{producto_id}")
                )
                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

        return render_template('exito_compra.html', producto=producto, cantidad=cantidad)

    return render_template('comprar.html', producto=producto, nombre_usuario=session.get('nombre'))


@app.route('/productos/eliminar/<int:id>', methods=['POST'])
def eliminar_producto(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM productos WHERE id = %s", (id,))
        conn.commit()
    conn.close()

    return redirect(url_for('productos'))


@app.route('/productos/editar/<int:id>', methods=['GET', 'POST'])
def editar_producto(id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        precio = request.form['precio']
        talla = request.form['talla']
        stock = request.form['stock']
        imagen = request.form.get('imagen', '')

        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE productos SET nombre = %s, descripcion = %s, precio = %s, talla = %s, stock = %s, imagen = %s WHERE id = %s",
                (nombre, descripcion, precio, talla, stock, imagen, id)
            )
            conn.commit()
        conn.close()
        return redirect(url_for('productos'))

    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM productos WHERE id = %s", (id,))
        producto = cursor.fetchone()
    conn.close()

    if not producto:
        return redirect(url_for('productos'))

    return render_template('editar_producto.html', producto=producto, rol=session.get('rol'))


@app.route('/ubicacion')
def ubicacion_modulo():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return render_template('ubicacion.html', rol=session.get('rol'))


@app.route('/encuesta', methods=['GET', 'POST'])
def encuesta_modulo():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    mensaje = None
    if request.method == 'POST':
        calificacion = request.form.get('calificacion')
        atencion = request.form.get('atencion')
        comentarios = request.form.get('comentarios')
        mejora = request.form.get('mejora')
        recomendacion = request.form.get('recomendacion')

        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO encuestas (usuario_id, calificacion, atencion, comentarios, mejora, recomendacion) VALUES (%s, %s, %s, %s, %s, %s)",
                (session['usuario_id'], calificacion, atencion, comentarios, mejora, recomendacion)
            )
            cursor.execute(
                "INSERT INTO eventos (usuario_id, evento, ruta) VALUES (%s, %s, %s)",
                (session['usuario_id'], f"Encuesta respondida ({calificacion}/5 estrellas)", '/encuesta')
            )
            conn.commit()
        conn.close()

        mensaje = "¡Gracias por tus comentarios! Tu opinión nos ayuda a mejorar."

    return render_template(
        'encuesta.html',
        mensaje=mensaje,
        nombre_usuario=session.get('nombre'),
        rol=session.get('rol')
    )


@app.route('/chat', methods=['GET', 'POST'])
def chat_modulo():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conexion = get_db_connection()
    cursor = conexion.cursor()

    if request.method == 'POST':
        mensaje = request.form.get('mensaje')
        usuario_id = session['usuario_id']
        nombre_usuario = session.get('nombre', 'Cliente')

        if mensaje:
            cursor.execute(
                "INSERT INTO chat (usuario_id, nombre_usuario, mensaje) VALUES (%s, %s, %s)",
                (usuario_id, nombre_usuario, mensaje)
            )
            conexion.commit()

    cursor.execute("DELETE FROM chat WHERE creado_en < NOW() - INTERVAL 2 HOUR")
    conexion.commit()

    cursor.execute("SELECT usuario_id, nombre_usuario, mensaje, creado_en FROM chat ORDER BY creado_en ASC")
    mensajes = cursor.fetchall()

    cursor.close()
    conexion.close()

    return render_template(
        'chat.html',
        mensajes=mensajes,
        usuario_actual=session.get('usuario_id'),
        nombre_actual=session.get('nombre'),
        rol=session.get('rol')
    )


# ----------------------------------------------------
# MÓDULO DE FOTOS, CÁMARA Y ARCHIVOS
# ----------------------------------------------------
@app.route('/video', methods=['GET', 'POST'])
def video_modulo():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))

    conn = get_db_connection()

    if request.method == 'POST':
        comentario = request.form.get('comentario')
        modelo = request.form.get('modelo')
        talla = request.form.get('talla')
        foto_base64 = request.form.get('foto_base64')

        modelo_completo = f"{modelo} (Talla: {talla})" if talla else modelo

        if foto_base64 and modelo:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO fotos_compras (usuario_id, nombre_usuario, imagen, comentario, modelo) VALUES (%s, %s, %s, %s, %s)",
                    (session['usuario_id'], session.get('nombre'), foto_base64, comentario, modelo_completo)
                )
                conn.commit()
        conn.close()
        return redirect(url_for('video_modulo'))

    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM fotos_compras ORDER BY id DESC")
        publicaciones = cursor.fetchall()

        cursor.execute("SELECT id, nombre, talla FROM productos ORDER BY nombre ASC")
        productos = cursor.fetchall()
    conn.close()

    return render_template(
        'fotos.html',
        publicaciones=publicaciones,
        productos=productos,
        nombre_usuario=session.get('nombre'),
        rol=session.get('rol')
    )


@app.route('/video/eliminar/<int:foto_id>', methods=['POST'])
def eliminar_foto_comunidad(foto_id):
    if 'usuario_id' not in session or session.get('rol') != 'admin':
        return redirect(url_for('video_modulo'))

    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM fotos_compras WHERE id = %s", (foto_id,))
        conn.commit()
    conn.close()

    return redirect(url_for('video_modulo'))


@app.route('/carrito')
def carrito_modulo():
    if 'usuario_id' not in session:
        return redirect(url_for('login'))
    return render_template('carrito.html', nombre=session.get('nombre'))


@app.route('/api/comprar-carrito', methods=['POST'])
def api_comprar_carrito():
    if 'usuario_id' not in session:
        return jsonify({'ok': False, 'error': 'Sesión no iniciada'}), 401

    data = request.get_json(silent=True) or {}
    items = data.get('items', [])
    latitud = data.get('latitud')
    longitud = data.get('longitud')

    if not items:
        return jsonify({'ok': False, 'error': 'El carrito está vacío'}), 400

    lat_val = float(latitud) if latitud not in (None, '') else None
    lng_val = float(longitud) if longitud not in (None, '') else None

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            for item in items:
                prod_id = int(item.get('id'))
                cantidad = int(item.get('cantidad', 1))
                talla = item.get('talla')

                cursor.execute("SELECT id, nombre, precio, stock, talla FROM productos WHERE id = %s", (prod_id,))
                prod = cursor.fetchone()
                if not prod or cantidad < 1 or cantidad > prod['stock']:
                    conn.rollback()
                    return jsonify({'ok': False, 'error': f"Stock insuficiente para {item.get('nombre', 'producto')}"}), 400

                precio_unitario = float(prod['precio'])
                total = round(precio_unitario * cantidad, 2)
                talla_final = talla or prod.get('talla')

                cursor.execute("UPDATE productos SET stock = stock - %s WHERE id = %s", (cantidad, prod_id))

                cursor.execute(
                    """
                    INSERT INTO compras (usuario_id, producto_id, talla, cantidad, precio_unitario, total, latitud, longitud)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (session['usuario_id'], prod_id, talla_final, cantidad, precio_unitario, total, lat_val, lng_val)
                )

                if lat_val is not None and lng_val is not None:
                    cursor.execute(
                        "INSERT INTO ubicaciones (usuario_id, nombre, latitud, longitud, precision_m) VALUES (%s, %s, %s, %s, %s)",
                        (session['usuario_id'], f"Compra carrito: {prod['nombre']} (Cant: {cantidad})", lat_val, lng_val, 10)
                    )

                cursor.execute(
                    "INSERT INTO eventos (usuario_id, evento, ruta) VALUES (%s, %s, %s)",
                    (session['usuario_id'], f"Compra en carrito ({cantidad}x {prod['nombre']})", '/carrito')
                )
            conn.commit()
        return jsonify({'ok': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        conn.close()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)