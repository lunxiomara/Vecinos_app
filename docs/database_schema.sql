-- ==============================================================
-- SISTEMA VECINOS APP - ESQUEMA RELACIONAL (M1 & M2)
-- Motor: MariaDB / MySQL (InnoDB)
-- Codificación: UTF-8 (utf8mb4_unicode_ci)
-- ==============================================================

USE vecinos;

-- ==============================================================
-- 1. EDIFICIO (Tenant principal / Unidad de aislamiento)
-- ==============================================================
CREATE TABLE IF NOT EXISTS incidencias_edificio (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    direccion VARCHAR(200) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==============================================================
-- 2. UNIDAD RESIDENCIAL (Apartamentos / Casas / Locales)
-- ==============================================================
CREATE TABLE IF NOT EXISTS incidencias_unidad (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    edificio_id BIGINT NOT NULL,
    numero VARCHAR(20) NOT NULL COMMENT 'Ej: 101, 204B',
    piso VARCHAR(10) NOT NULL,
    CONSTRAINT fk_unidad_edificio 
        FOREIGN KEY (edificio_id) REFERENCES incidencias_edificio(id) 
        ON DELETE CASCADE,
    CONSTRAINT uq_edificio_unidad UNIQUE (edificio_id, numero)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==============================================================
-- 3. PERFIL EXTENDIDO (Roles: residente, administrador, técnico, auditor)
-- ==============================================================
CREATE TABLE IF NOT EXISTS incidencias_perfil (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    edificio_id BIGINT NOT NULL,
    unidad_id BIGINT NULL,
    rol VARCHAR(20) NOT NULL DEFAULT 'residente',
    piso VARCHAR(10) NOT NULL DEFAULT '',
    puerta VARCHAR(10) NOT NULL DEFAULT '',
    CONSTRAINT fk_perfil_user 
        FOREIGN KEY (user_id) REFERENCES auth_user(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_perfil_edificio 
        FOREIGN KEY (edificio_id) REFERENCES incidencias_edificio(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_perfil_unidad 
        FOREIGN KEY (unidad_id) REFERENCES incidencias_unidad(id) 
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==============================================================
-- 4. INCIDENCIAS (Con aislamiento por edificio y máquina de estados)
-- ==============================================================
CREATE TABLE IF NOT EXISTS incidencias_incidencia (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    edificio_id BIGINT NULL,
    creador_id INT NOT NULL,
    tecnico_asignado VARCHAR(100) NULL,
    titulo VARCHAR(150) NOT NULL,
    descripcion LONGTEXT NOT NULL,
    categoria VARCHAR(20) NOT NULL DEFAULT 'otros',
    prioridad VARCHAR(10) NOT NULL DEFAULT 'media',
    estado VARCHAR(15) NOT NULL DEFAULT 'pendiente',
    foto VARCHAR(100) NULL,
    nota_interna LONGTEXT NULL,
    fecha_creacion DATETIME(6) NOT NULL,
    fecha_actualizacion DATETIME(6) NOT NULL,
    CONSTRAINT fk_incidencia_edificio 
        FOREIGN KEY (edificio_id) REFERENCES incidencias_edificio(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_incidencia_creador 
        FOREIGN KEY (creador_id) REFERENCES auth_user(id) 
        ON DELETE CASCADE,
    INDEX idx_incidencia_edificio_estado (edificio_id, estado),
    INDEX idx_incidencia_prioridad (prioridad)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==============================================================
-- 5. COMENTARIOS
-- ==============================================================
CREATE TABLE IF NOT EXISTS incidencias_comentario (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    incidencia_id BIGINT NOT NULL,
    autor_id INT NOT NULL,
    mensaje LONGTEXT NOT NULL,
    es_interno TINYINT(1) NOT NULL DEFAULT 0,
    fecha_creacion DATETIME(6) NOT NULL,
    CONSTRAINT fk_comentario_incidencia 
        FOREIGN KEY (incidencia_id) REFERENCES incidencias_incidencia(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_comentario_autor 
        FOREIGN KEY (autor_id) REFERENCES auth_user(id) 
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==============================================================
-- 6. EVENTO INCIDENCIA (Historial inmutable de auditoría / Append-Only)
-- ==============================================================
CREATE TABLE IF NOT EXISTS incidencias_eventoincidencia (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    incidencia_id BIGINT NOT NULL,
    actor_id INT NULL,
    tipo VARCHAR(30) NOT NULL,
    estado_antes VARCHAR(15) NULL,
    estado_despues VARCHAR(15) NULL,
    detalle LONGTEXT NOT NULL DEFAULT '',
    fecha DATETIME(6) NOT NULL,
    CONSTRAINT fk_evento_incidencia 
        FOREIGN KEY (incidencia_id) REFERENCES incidencias_incidencia(id) 
        ON DELETE CASCADE,
    CONSTRAINT fk_evento_actor 
        FOREIGN KEY (actor_id) REFERENCES auth_user(id) 
        ON DELETE SET NULL,
    INDEX idx_evento_incidencia_fecha (incidencia_id, fecha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
