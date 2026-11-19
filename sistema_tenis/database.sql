CREATE DATABASE IF NOT EXISTS sistema_tenis_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE sistema_tenis_db;

def get_db_connection():
    return pymysql.connect(
        host='localhost',
        user='root',
        password='12345678',           # Si configuraste contraseña en tu MySQL de XAMPP, ponla aquí entre las comillas. Si no, déjala vacía ''.
        database='sistema_tenis_db', # Nombre exacto de la base de datos que creamos con el script .sql
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

-- Tabla de Usuarios con distinción de rol (Admin o Client)
CREATE TABLE IF NOT EXISTS usuarios (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    nombre        VARCHAR(100) NOT NULL,
    correo        VARCHAR(150) NOT NULL UNIQUE,
    rol           ENUM('admin', 'client') NOT NULL DEFAULT 'client',
    password_hash VARCHAR(255) NOT NULL,
    creado_en     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Productos / Servicios (Catálogo de Tenis)
CREATE TABLE IF NOT EXISTS productos (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    nombre      VARCHAR(150) NOT NULL,
    descripcion TEXT NOT NULL,
    precio      DECIMAL(10,2) NOT NULL,
    talla       VARCHAR(20) NOT NULL,
    stock       INT NOT NULL DEFAULT 0,
    imagen      VARCHAR(255) NULL,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabla de Ubicaciones (Módulo Geolocalización)
CREATE TABLE IF NOT EXISTS ubicaciones (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id  INT NULL,
    nombre      VARCHAR(100) NOT NULL,
    latitud     DECIMAL(10, 8) NOT NULL,
    longitud    DECIMAL(11, 8) NOT NULL,
    precision_m INT UNSIGNED NOT NULL,
    creado_en   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- Tabla de Fotos (Módulo de Cámara y Galería)
CREATE TABLE IF NOT EXISTS fotos (
    id         INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NULL,
    nombre     VARCHAR(100) NOT NULL,
    archivo    VARCHAR(150) NOT NULL UNIQUE,
    tipo       VARCHAR(20) NOT NULL,
    bytes      INT UNSIGNED NOT NULL,
    creado_en  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- Tabla de Métricas y Eventos (Dashboard Admin)
CREATE TABLE IF NOT EXISTS eventos (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id   INT NULL,
    visitante_id VARCHAR(100) NULL,
    evento       VARCHAR(100) NOT NULL,
    ruta         VARCHAR(255) NOT NULL,
    creado_en    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- Insertar un Administrador por defecto (Contraseña: admin123)
INSERT INTO usuarios (nombre, correo, rol, password_hash) 
VALUES ('Administrador Master', 'admin@tenis.com', 'admin', '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2.uheWG/igi')
ON DUPLICATE KEY UPDATE id=id;