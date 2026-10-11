--DROP TABLE IF EXISTS detalle_cuenta;
--DROP TABLE IF EXISTS cuenta;
--DROP TABLE IF EXISTS reserva;
--DROP TABLE IF EXISTS plato;
--DROP TABLE IF EXISTS categoria;
--DROP TABLE IF EXISTS tematica;
--DROP TABLE IF EXISTS mesa;
--DROP TABLE IF EXISTS usuario;

CREATE TABLE usuario (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre    TEXT NOT NULL,
    email     TEXT NOT NULL UNIQUE,
    password  TEXT NOT NULL,
    rol       TEXT NOT NULL DEFAULT 'cliente' CHECK (rol IN ('cliente','admin'))
);

CREATE TABLE mesa (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    numero     INTEGER NOT NULL UNIQUE,
    capacidad  INTEGER NOT NULL,
    estado     TEXT NOT NULL DEFAULT 'libre'
);

CREATE TABLE tematica (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre  TEXT NOT NULL UNIQUE
);

CREATE TABLE categoria (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre  TEXT NOT NULL UNIQUE
);

CREATE TABLE plato (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    categoria_id  INTEGER NOT NULL,
    nombre        TEXT NOT NULL,
    descripcion   TEXT,
    precio        REAL NOT NULL,
    imagen        TEXT,                       -- nombre del archivo
    disponible    INTEGER NOT NULL DEFAULT 1, -- 1 = sí, 0 = no
    FOREIGN KEY (categoria_id) REFERENCES categoria(id)
);

CREATE TABLE reserva (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id         INTEGER NOT NULL,
    mesa_id            INTEGER NOT NULL,
    tematica_id        INTEGER,
    fecha              TEXT NOT NULL,         -- 'YYYY-MM-DD'
    hora_inicio        TEXT NOT NULL,         -- 'HH:MM'
    hora_fin           TEXT NOT NULL,
    cantidad_personas  INTEGER NOT NULL,
    estado             TEXT NOT NULL DEFAULT 'pendiente',
    observaciones      TEXT,
    FOREIGN KEY (usuario_id)  REFERENCES usuario(id),
    FOREIGN KEY (mesa_id)     REFERENCES mesa(id),
    FOREIGN KEY (tematica_id) REFERENCES tematica(id)
);

CREATE TABLE cuenta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mesa_id         INTEGER NOT NULL,
    fecha_apertura  TEXT NOT NULL,
    hora_apertura   TEXT NOT NULL,
    hora_cierre     TEXT,
    estado          TEXT NOT NULL DEFAULT 'abierta',
    total           REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (mesa_id) REFERENCES mesa(id)
);

CREATE TABLE detalle_cuenta (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    cuenta_id        INTEGER NOT NULL,
    plato_id         INTEGER NOT NULL,
    cantidad         INTEGER NOT NULL,
    precio_unitario  REAL NOT NULL,
    subtotal         REAL NOT NULL,
    FOREIGN KEY (cuenta_id) REFERENCES cuenta(id),
    FOREIGN KEY (plato_id)  REFERENCES plato(id)
);

-- =====================================================
-- DATOS INICIALES - PIZZATRO (restaurante italiano)
-- Ejecutar DESPUÉS de crear las tablas con schema.sql
-- Precios en pesos colombianos (COP).
-- =====================================================
-- IMÁGENES: cada plato tiene el nombre del archivo correspondiente.
-- =====================================================


-- ---------- TEMÁTICAS ----------
-- (Si una reserva no tiene temática, tematica_id queda en NULL)
INSERT INTO tematica (nombre) VALUES
('Cumpleaños'),
('Aniversario'),
('Corporativo');


-- ---------- CATEGORÍAS ----------
-- id 1 = Entrada, 2 = Plato fuerte, 3 = Postre
INSERT INTO categoria (nombre) VALUES
('Entrada'),
('Plato fuerte'),
('Postre');


-- ---------- MESAS (30) ----------
INSERT INTO mesa (numero, capacidad, estado) VALUES
(1,  2,  'libre'),
(2,  2,  'libre'),
(3,  4,  'libre'),
(4,  4,  'libre'),
(5,  2,  'libre'),
(6,  6,  'libre'),
(7,  4,  'libre'),
(8,  4,  'libre'),
(9,  2,  'libre'),
(10, 8,  'libre'),
(11, 4,  'libre'),
(12, 6,  'libre'),
(13, 2,  'libre'),
(14, 4,  'libre'),
(15, 4,  'libre'),
(16, 6,  'libre'),
(17, 2,  'libre'),
(18, 4,  'libre'),
(19, 8,  'libre'),
(20, 4,  'libre'),
(21, 6,  'libre'),
(22, 2,  'libre'),
(23, 4,  'libre'),
(24, 10, 'libre'),
(25, 4,  'libre'),
(26, 6,  'libre'),
(27, 2,  'libre'),
(28, 8,  'libre'),
(29, 4,  'libre'),
(30, 10, 'libre');


-- ---------- PLATOS ----------
-- Columnas: categoria_id, nombre, descripcion, precio, imagen, disponible

-- ===== ENTRADAS (categoria_id = 1) =====
INSERT INTO plato (categoria_id, nombre, descripcion, precio, imagen, disponible) VALUES
(1, 'Bruschetta Clásica',
    'Pan artesanal tostado con tomate fresco, albahaca, ajo y aceite de oliva extra virgen.',
    18000, 'Bruschetta Clásica.png', 1),
(1, 'Ensalada Caprese',
    'Mozzarella fresca, tomate maduro y hojas de albahaca con reducción de balsámico.',
    22000, 'Ensalada Caprese.png', 1),
(1, 'Carpaccio di Manzo',
    'Láminas finas de lomo de res con rúcula, parmesano y limón.',
    32000, 'Carpaccio di Manzo.png', 1),
(1, 'Calamares Fritti',
    'Anillos de calamar crocantes con salsa marinara y limón.',
    29000, 'Calamares Fritti.png', 1),
(1, 'Arancini di Risotto',
    'Croquetas de risotto rellenas de mozzarella, empanizadas y fritas.',
    24000, 'Arancini di Risotto.png', 1),
(1, 'Focaccia al Rosmarino',
    'Pan plano horneado con romero, sal marina y aceite de oliva.',
    16000, 'Focaccia al Rosmarino.png', 1),
(1, 'Zuppa Minestrone',
    'Sopa italiana de verduras de temporada, legumbres y pasta pequeña.',
    19000, 'Zuppa Minestrone.png', 1),
(1, 'Burrata con Tomates Cherry',
    'Burrata cremosa con tomates cherry confitados',
    30000, 'Burrata con Tomates Cherry.png', 1),
(1, 'Antipasto Misto',
    'Tabla de jamón curado, salami, quesos, aceitunas y vegetales en conserva.',
    38000, 'Antipasto Misto.png', 1);

-- ===== PLATOS FUERTES (categoria_id = 2) =====
INSERT INTO plato (categoria_id, nombre, descripcion, precio, imagen, disponible) VALUES
(2, 'Pizza Margherita',
    'Salsa de tomate San Marzano, mozzarella fior di latte, albahaca y aceite de oliva.',
    36000, 'Pizza-Margherita.png', 1),
(2, 'Pizza Pepperoni',
    'Mozzarella, salsa de tomate y abundante pepperoni artesanal.',
    42000, 'Pizza-Pepperoni.png', 1),
(2, 'Pizza Quattro Formaggi',
    'Mozzarella, gorgonzola, parmesano y provolone sobre base blanca.',
    46000, 'Pizza-Quattro-Formaggi.png', 1),
(2, 'Spaghetti alla Carbonara',
    'Spaghetti con panceta crocante, yema de huevo, pecorino y pimienta negra.',
    41000, 'Spaghetti-alla-Carbonara.png', 1),
(2, 'Fettuccine Alfredo',
    'Fettuccine en salsa cremosa de mantequilla y parmesano, con pollo opcional.',
    39000, 'Fettuccine-Alfredo.png', 1),
(2, 'Lasagna alla Bolognese',
    'Capas de pasta fresca, ragú de res y cerdo, bechamel y queso gratinado.',
    44000, 'Lasagna-alla-Bolognese.png', 1),
(2, 'Gnocchi al Pesto',
    'Ñoquis de papa caseros con pesto genovés, piñones y parmesano.',
    40000, 'Gnocchi-al-Pesto.png', 1),
(2, 'Risotto ai Funghi',
    'Arroz arborio cremoso con mezcla de hongos, vino blanco y parmesano.',
    45000, 'Risotto-ai-Funghi.png', 1),
(2, 'Pollo alla Parmigiana',
    'Pechuga apanada con salsa pomodoro y mozzarella gratinada, con pasta.',
    48000, 'Pollo-alla-Parmigiana.png', 1);

-- ===== POSTRES (categoria_id = 3) =====
INSERT INTO plato (categoria_id, nombre, descripcion, precio, imagen, disponible) VALUES
(3, 'Tiramisù',
    'Clásico postre de mascarpone, café espresso, bizcochos y cacao.',
    19000, 'Tiramisù.png', 1),
(3, 'Panna Cotta',
    'Crema de vainilla con coulis de frutos rojos.',
    17000, 'Panna Cotta.png', 1),
(3, 'Cannoli Siciliani',
    'Tubos crocantes rellenos de crema de ricotta con chips de chocolate.',
    18000, 'Cannoli Siciliani.png', 1),
(3, 'Affogato al Caffè',
    'Helado de vainilla bañado en espresso caliente.',
    14000, 'Affogato al Caffè.png', 1),
(3, 'Torta Caprese',
    'Torta de chocolate y almendras, sin harina, suave y húmeda.',
    20000, 'Torta Caprese.png', 1),
(3, 'Semifreddo al Limone',
    'Postre helado cremoso de limón con base de galleta.',
    18000, 'Semifreddo al Limone.png', 1),
(3, 'Zeppole',
    'Buñuelos italianos fritos con azúcar glass y crema pastelera.',
    16000, 'Zeppole.png', 1),
(3, 'Torta della Nonna',
    'Tarta de crema pastelera con piñones y azúcar glass.',
    19000, 'Torta della Nonna.png', 1);


INSERT INTO usuario (nombre, email , password,  rol) VALUES
('Juan David Lopez Yara', 'juandavidlopezyara65@gmail.com',
'scrypt:32768:8:1$nkyeqZXVXNrxj96i$76123182c87a6ba690ef6de7f192ce5c3848a25089707f9cc03bcc7c9df2c958da4153008f7624926c902bae114030a2b917495e902f454d4bfc8dd1f2091c8e'
,'admin');
