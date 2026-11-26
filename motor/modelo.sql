CREATE TABLE IF NOT EXISTS dim_fecha (
    fecha_id INTEGER PRIMARY KEY,
    fecha_iso DATE NOT NULL UNIQUE,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL CHECK (mes BETWEEN 1 AND 12),
    dia INTEGER NOT NULL CHECK (dia BETWEEN 1 AND 31)
);
CREATE TABLE IF NOT EXISTS dim_producto (
    producto_id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL,
    categoria VARCHAR(40) NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_cliente (
    cliente_id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_canal (
    canal_id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL
);
CREATE TABLE IF NOT EXISTS dim_ubicacion (
    ubicacion_id VARCHAR(20) PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL
);
CREATE TABLE IF NOT EXISTS hecho_venta (
    comprobante VARCHAR(32) NOT NULL,
    linea INTEGER NOT NULL CHECK (linea > 0),
    fecha_id INTEGER NOT NULL REFERENCES dim_fecha(fecha_id),
    producto_id VARCHAR(20) NOT NULL REFERENCES dim_producto(producto_id),
    cliente_id VARCHAR(20) NOT NULL REFERENCES dim_cliente(cliente_id),
    canal_id VARCHAR(20) NOT NULL REFERENCES dim_canal(canal_id),
    cantidad_g BIGINT NOT NULL CHECK (cantidad_g > 0),
    precio_kg_cent BIGINT NOT NULL CHECK (precio_kg_cent > 0),
    bruto_cent BIGINT NOT NULL CHECK (bruto_cent >= 0),
    descuento_cent BIGINT NOT NULL CHECK (descuento_cent >= 0 AND descuento_cent <= bruto_cent),
    neto_cent BIGINT NOT NULL CHECK (neto_cent = bruto_cent - descuento_cent),
    PRIMARY KEY (comprobante, linea)
);
CREATE INDEX IF NOT EXISTS ix_venta_fecha ON hecho_venta(fecha_id);
CREATE INDEX IF NOT EXISTS ix_venta_producto ON hecho_venta(producto_id);
CREATE TABLE IF NOT EXISTS hecho_inventario (
    fecha_id INTEGER NOT NULL REFERENCES dim_fecha(fecha_id),
    producto_id VARCHAR(20) NOT NULL REFERENCES dim_producto(producto_id),
    ubicacion_id VARCHAR(20) NOT NULL REFERENCES dim_ubicacion(ubicacion_id),
    saldo_g BIGINT NOT NULL CHECK (saldo_g >= 0),
    PRIMARY KEY (fecha_id, producto_id, ubicacion_id)
);
CREATE TABLE IF NOT EXISTS bitacora_etl (
    fuente VARCHAR(32) PRIMARY KEY,
    extraidas INTEGER NOT NULL,
    aceptadas INTEGER NOT NULL,
    duplicadas INTEGER NOT NULL,
    rechazadas INTEGER NOT NULL,
    CHECK (extraidas = aceptadas + duplicadas + rechazadas)
);
CREATE TABLE IF NOT EXISTS incidencia_etl (
    fuente VARCHAR(32) NOT NULL REFERENCES bitacora_etl(fuente),
    fila INTEGER NOT NULL,
    clave VARCHAR(100) NOT NULL,
    tipo VARCHAR(20) NOT NULL,
    motivo VARCHAR(160) NOT NULL,
    PRIMARY KEY (fuente, fila)
);
