import decimal
import logging
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
import psycopg2
from psycopg2 import OperationalError, DatabaseError, IntegrityError, Error as Psycopg2Error
from psycopg2 import errors as pg_errors

app = Flask(__name__)

# --- Configuración de base de datos ---
DB_CONFIG = {
    'host': 'localhost',
    'database': 'mi_bd',
    'user': 'mi_usuario',
    'password': 'mi_contraseña',
    'port': 5432
}

# Flags para activar/desactivar endpoints
LISTAR_FACTURAS_ENDPOINT_ACTIVE = True
VER_FACTURA_ENDPOINT_ACTIVE = True
NUEVA_FACTURA_ENDPOINT_ACTIVE = True
LISTAR_CLIENTES_ENDPOINT_ACTIVE = True
LISTAR_PRODUCTOS_ENDPOINT_ACTIVE = True

# Configurar logger
handler = logging.StreamHandler()
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)


def get_db_connection(config=None):
    """
    Devuelve una conexión psycopg2, usando `config` o `DB_CONFIG` si es None.
    Valida tipos y claves mínimas, ignora extras.
    """
    cfg = config if config is not None else DB_CONFIG
    if not isinstance(cfg, dict):
        raise TypeError("El parámetro config debe ser un dict")
    # Claves requeridas
    for key in ('host', 'database', 'user', 'password'):
        if key not in cfg:
            raise KeyError(f"Falta la clave obligatoria en DB_CONFIG: {key}")
    # Intentar conectar
    try:
        return psycopg2.connect(
            host=cfg['host'],
            database=cfg['database'],
            user=cfg['user'],
            password=cfg['password'],
            port=cfg.get('port', DB_CONFIG.get('port'))
        )
    except Exception as e:
        app.logger.error("Error al conectar a la BD", exc_info=True)
        raise


# --- Manejo de errores global --- #

@app.errorhandler(404)
def handle_404(e):
    return render_template('404.html'), 404

@app.errorhandler(405)
def handle_405(e):
    return render_template('405.html'), 405

@app.errorhandler(500)
def handle_500(e):
    # Si la respuesta ya es JSON (viene de jsonify), Flask lo respeta
    if request.accept_mimetypes.accept_json and not request.path.startswith(('/clientes', '/productos', '/facturas', '/factura', '/agregar_cliente')):
        return jsonify(error="Error interno inesperado", details=str(e)), 500
    return render_template('500.html', error=str(e)), 500


# --- Rutas de facturas --- #

@app.route('/')
def index():
    # Redirige a lista de facturas
    if not LISTAR_FACTURAS_ENDPOINT_ACTIVE:
        abort(404)
    try:
        return redirect(url_for('listar_facturas'))
    except Exception as e:
        app.logger.error("Error en url_for listar_facturas", exc_info=True)
        abort(500)


@app.route('/facturas/')
def listar_facturas():
    if not LISTAR_FACTURAS_ENDPOINT_ACTIVE:
        return jsonify(error="Endpoint 'listar_facturas' no disponible."), 404

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'SELECT f.id, f.numero, f.fecha, c.nombre as cliente, f.total '
            'FROM facturas f JOIN clientes c ON f.cliente_id = c.id '
            'ORDER BY f.fecha DESC;'
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            return render_template('facturas.html', facturas=[], empty_message="No hay facturas disponibles."), 200

        return render_template('facturas.html', facturas=rows), 200

    except OperationalError as e:
        app.logger.error("Error de base de datos al listar facturas", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500
    except DatabaseError as e:
        app.logger.error("Error de base de datos al listar facturas", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500
    except Exception as e:
        app.logger.error("Error interno inesperado en listar_facturas", exc_info=True)
        return jsonify(error="Error interno inesperado", details=str(e)), 500


@app.route('/factura/<int:factura_id>')
def ver_factura(factura_id):
    if not VER_FACTURA_ENDPOINT_ACTIVE:
        return jsonify(error="Endpoint 'ver_factura' no disponible."), 404

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Detalle factura
        cur.execute(
            '''
            SELECT f.id, f.numero, f.fecha, f.total,
                   c.id as cliente_id, c.nombre as cliente_nombre,
                   c.direccion as cliente_direccion, c.telefono as cliente_telefono,
                   COALESCE(f.estado, 'ACTIVA') as estado
            FROM facturas f JOIN clientes c ON f.cliente_id = c.id
            WHERE f.id = %s;
            ''', (factura_id,)
        )
        factura = cur.fetchone()
        if factura is None:
            cur.close()
            conn.close()
            return render_template('ver_factura.html', error="Factura no encontrada"), 404

        # Items
        cur.execute(
            '''
            SELECT fi.id, p.nombre as producto, fi.cantidad, fi.precio, fi.subtotal
            FROM factura_items fi JOIN productos p ON fi.producto_id = p.id
            WHERE fi.factura_id = %s;
            ''', (factura_id,)
        )
        items = cur.fetchall()
        cur.close()
        conn.close()

        return render_template(
            'ver_factura.html',
            factura=factura,
            items=items,
            empty_items_message="No hay items en esta factura."
        ), 200

    except OperationalError as e:
        app.logger.error("Error de base de datos en ver_factura", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500
    except DatabaseError as e:
        app.logger.error("Error de base de datos en ver_factura", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500
    except Exception as e:
        app.logger.error("Error interno inesperado en ver_factura", exc_info=True)
        return jsonify(error="Error interno inesperado", details=str(e)), 500


@app.route('/factura/nueva', methods=['GET', 'POST'])
def nueva_factura():
    if not NUEVA_FACTURA_ENDPOINT_ACTIVE:
        return jsonify(error="Endpoint 'nueva_factura' no disponible."), 404

    if request.method == 'GET':
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT id, nombre FROM clientes ORDER BY nombre;')
            clientes = cur.fetchall()
            cur.execute('SELECT id, nombre, precio FROM productos ORDER BY nombre;')
            productos = cur.fetchall()
            cur.close()
            conn.close()
            return render_template('nueva_factura.html', clientes=clientes, productos=productos), 200

        except Exception as e:
            app.logger.error("Error al preparar nueva factura", exc_info=True)
            return jsonify(error="Error de base de datos", details=str(e)), 500

    # POST
    try:
        form = request.form
        cliente_id = form.get('cliente_id', '').strip()
        if not cliente_id or not cliente_id.isdigit():
            raise ValueError("cliente_id inválido")
        cliente_id = int(cliente_id)

        # Obtener items del form
        items = []
        for key in form:
            if key.startswith('producto_id_') and form.get(key):
                idx = key.split('_')[-1]
                pid = form.get(f'producto_id_{idx}').strip()
                qty = form.get(f'cantidad_{idx}', '').strip()
                if not pid.isdigit() or not qty:
                    raise ValueError("producto o cantidad inválidos")
                qty_f = decimal.Decimal(qty)
                if qty_f <= 0:
                    raise ValueError("cantidad no puede ser <= 0")
                items.append((int(pid), qty_f))

        # Calcular total y secuencia
        conn = get_db_connection()
        cur = conn.cursor()

        total = decimal.Decimal('0')
        precios = {}
        for pid, qty in items:
            cur.execute('SELECT precio FROM productos WHERE id = %s;', (pid,))
            row = cur.fetchone()
            if not row:
                raise ValueError("producto no encontrado o sin precio")
            precio = decimal.Decimal(row[0])
            precios[pid] = precio
            total += precio * qty

        # Número factura
        cur.execute("SELECT nextval('factura_numero_seq');")
        seq = cur.fetchone()[0]
        numero = f"FACT-{seq}"

        # Insertar factura
        cur.execute(
            'INSERT INTO facturas (numero, cliente_id, total) VALUES (%s, %s, %s) RETURNING id;',
            (numero, cliente_id, total)
        )
        factura_id = cur.fetchone()[0]

        # Insertar items
        for pid, qty in items:
            precio = precios[pid]
            subtotal = precio * qty
            cur.execute(
                'INSERT INTO factura_items (factura_id, producto_id, cantidad, precio, subtotal) '
                'VALUES (%s, %s, %s, %s, %s);',
                (factura_id, pid, str(qty), precio, subtotal)
            )

        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('ver_factura', factura_id=factura_id))

    except (OperationalError, DatabaseError, IntegrityError, Psycopg2Error, ValueError) as e:
        app.logger.error("Error de base de datos o validación en nueva_factura", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback", exc_info=True)
        return jsonify(error="Error de base de datos" if isinstance(e, Psycopg2Error) else "Error de validación", details=str(e)), 500
    except Exception as e:
        app.logger.error("Error interno inesperado en nueva_factura", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback", exc_info=True)
        return jsonify(error="Error interno inesperado", details=str(e)), 500


# --- Rutas de clientes --- #

@app.route('/clientes')
def listar_clientes():
    if not LISTAR_CLIENTES_ENDPOINT_ACTIVE:
        abort(404)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, nombre, direccion, telefono, email FROM clientes ORDER BY nombre;')
        clientes = cur.fetchall()
        cur.close()
        conn.close()
        if not clientes:
            return render_template('clientes.html', clientes=[], empty_message="No hay clientes disponibles."), 200
        return render_template('clientes.html', clientes=clientes), 200

    except Exception as e:
        app.logger.error("Error al listar clientes", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


@app.route('/agregar_cliente', methods=['GET', 'POST'])
def agregar_cliente():
    if request.method == 'GET':
        return render_template('agregar_cliente.html'), 200

    # POST
    data = request.form
    nombre = data.get('nombre', '').strip()
    direccion = data.get('direccion', '').strip()
    telefono = data.get('telefono', '').strip()
    email = data.get('email', '').strip()

    if not all([nombre, direccion, telefono, email]):
        return render_template('agregar_cliente.html', error="Todos los campos son obligatorios."), 200

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clientes (nombre, direccion, telefono, email) VALUES (%s, %s, %s, %s);",
            (nombre, direccion, telefono, email)
        )
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('listar_clientes'))

    except IntegrityError as e:
        app.logger.error("Error de unicidad al agregar cliente", exc_info=True)
        conn.rollback()
        return jsonify(error="Error de base de datos", details=str(e)), 500

    except Exception as e:
        app.logger.error("Error al agregar cliente", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback al agregar cliente", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


@app.route('/clientes/<int:cliente_id>/editar', methods=['GET'])
def editar_cliente(cliente_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, nombre, direccion, telefono, email FROM clientes WHERE id = %s;', (cliente_id,))
        cliente = cur.fetchone()
        cur.close()
        conn.close()
        if cliente is None:
            return render_template('editar_cliente.html', error="Cliente no encontrado"), 404
        return render_template('editar_cliente.html', cliente=cliente), 200

    except Exception as e:
        app.logger.error("Error al cargar datos para editar cliente", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


@app.route('/clientes/<int:cliente_id>/actualizar', methods=['POST'])
def actualizar_cliente(cliente_id):
    data = request.form
    nombre = data.get('nombre', '').strip()
    direccion = data.get('direccion', '').strip()
    telefono = data.get('telefono', '').strip()
    email = data.get('email', '').strip()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE clientes
            SET nombre = %s, direccion = %s, telefono = %s, email = %s
            WHERE id = %s;
            """,
            (nombre, direccion, telefono, email, cliente_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('listar_clientes'))

    except Exception as e:
        app.logger.error("Error al actualizar cliente", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback al actualizar cliente", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


@app.route('/eliminar_cliente/<int:cliente_id>', methods=['POST'])
def eliminar_cliente(cliente_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM facturas WHERE cliente_id = %s;', (cliente_id,))
        count = cur.fetchone()[0]
        if count > 0:
            # recargar lista
            cur.execute('SELECT id, nombre, direccion, telefono, email FROM clientes;')
            clientes = cur.fetchall()
            cur.close()
            conn.close()
            return render_template('clientes.html', clientes=clientes, error="No se puede eliminar el cliente porque tiene facturas asociadas."), 200

        cur.execute('DELETE FROM clientes WHERE id = %s;', (cliente_id,))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('listar_clientes'))

    except Exception as e:
        app.logger.error("Error al eliminar cliente", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback al eliminar cliente", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


# --- Rutas de productos --- #

@app.route('/productos')
def listar_productos():
    if not LISTAR_PRODUCTOS_ENDPOINT_ACTIVE:
        abort(404)
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id, nombre, descripcion, precio FROM productos ORDER BY nombre;')
        productos = cur.fetchall()
        cur.close()
        conn.close()
        if not productos:
            return render_template('productos.html', productos=[], empty_message="No hay productos disponibles."), 200
        return render_template('productos.html', productos=productos), 200

    except Exception as e:
        app.logger.error("Error al listar productos", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


@app.route('/productos/agregar', methods=['GET', 'POST'])
def agregar_producto():
    if request.method == 'GET':
        return render_template('agregar_producto.html'), 200

    data = request.form
    nombre = data.get('nombre', '').strip()
    descripcion = data.get('descripcion', '').strip()
    precio = data.get('precio', '').strip()

    if not all([nombre, descripcion, precio]):
        return render_template('agregar_producto.html', error="Todos los campos son obligatorios."), 200

    try:
        # validar float
        _ = decimal.Decimal(precio)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'INSERT INTO productos (nombre, descripcion, precio) VALUES (%s, %s, %s);',
            (nombre, descripcion, precio)
        )
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('listar_productos'))

    except IntegrityError as e:
        app.logger.error("Error de unicidad al agregar producto", exc_info=True)
        conn.rollback()
        return jsonify(error="Error de base de datos", details=str(e)), 500

    except Exception as e:
        app.logger.error("Error al agregar producto", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback al agregar producto", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


@app.route('/productos/editar/<int:producto_id>', methods=['GET', 'POST'])
def editar_producto(producto_id):
    if request.method == 'GET':
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('SELECT id, nombre, descripcion, precio FROM productos WHERE id = %s;', (producto_id,))
            prod = cur.fetchone()
            cur.close()
            conn.close()
            if prod is None:
                return render_template('editar_producto.html', error="Producto no encontrado"), 404
            return render_template('editar_producto.html', producto=prod), 200

        except Exception as e:
            app.logger.error("Error al cargar producto para editar", exc_info=True)
            return jsonify(error="Error de base de datos", details=str(e)), 500

    # POST
    data = request.form
    nombre = data.get('nombre', '').trim()
    descripcion = data.get('descripcion', '').trim()
    precio = data.get('precio', '').trim()

    try:
        _ = decimal.Decimal(precio)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            'UPDATE productos SET nombre = %s, descripcion = %s, precio = %s WHERE id = %s;',
            (nombre, descripcion, precio, producto_id)
        )
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('listar_productos'))

    except Exception as e:
        app.logger.error("Error al actualizar producto", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback al actualizar producto", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


@app.route('/productos/eliminar/<int:producto_id>', methods=['POST'])
def eliminar_producto(producto_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM productos WHERE id = %s;', (producto_id,))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('listar_productos'))

    except IntegrityError as e:
        # ForeignKeyViolation hereda de IntegrityError
        app.logger.error("FK violation al eliminar producto", exc_info=True)
        try:
            # refetch productos
            cur.execute('SELECT id, nombre, descripcion, precio FROM productos;')
            productos = cur.fetchall()
            conn.close()
            return render_template('productos.html', productos=productos, error="No se puede eliminar el producto porque se encuentra en una factura."), 200
        except Exception as e2:
            app.logger.error("Error al recargar productos tras FK violation", exc_info=True)
            conn.rollback()
            return jsonify(error="Error de base de datos", details=str(e2)), 500

    except Exception as e:
        app.logger.error("Error al eliminar producto", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            app.logger.error("Fallo en rollback al eliminar producto", exc_info=True)
        return jsonify(error="Error de base de datos", details=str(e)), 500


if __name__ == '__main__':
    app.run(debug=True)
