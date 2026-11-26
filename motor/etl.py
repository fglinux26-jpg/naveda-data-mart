import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter

from referencia import controles_origen, validar_conciliacion


RUTA = Path(__file__).resolve().parent
DIMENSIONES = {
    "productos": ("producto", "dim_producto", ["producto", "nombre", "categoria"]),
    "clientes": ("cliente", "dim_cliente", ["cliente", "nombre"]),
    "canales": ("canal", "dim_canal", ["canal", "nombre"]),
    "ubicaciones": ("ubicacion", "dim_ubicacion", ["ubicacion", "nombre"]),
}
TABLAS = ["dim_fecha", "dim_producto", "dim_cliente", "dim_canal", "dim_ubicacion",
          "hecho_venta", "hecho_inventario", "bitacora_etl", "incidencia_etl"]
VENTA = ["comprobante", "linea", "fecha", "producto", "cliente", "canal", "peso_kg", "precio_kg", "descuento_soles"]
STOCK = ["fecha", "producto", "ubicacion", "saldo_kg"]


def filas_csv(archivo, campos):
    with archivo.open(encoding="utf-8-sig", newline="") as stream:
        lector = csv.DictReader(stream)
        if list(lector.fieldnames or []) != campos:
            raise ValueError(f"Encabezados inesperados en {archivo.name}. Campos requeridos: {', '.join(campos)}.")
        for numero, fila in enumerate(lector, 2):
            if None in fila or any(v is None for v in fila.values()):
                raise ValueError(f"Estructura CSV incompleta o ambigua en {archivo.name}, fila {numero}.")
            yield numero, {k: v.strip() for k, v in fila.items()}


def fijo(texto, factor, minimo, campo):
    if not re.fullmatch(r"[+-]?\d{1,9}(?:\.\d{1,6})?", texto):
        raise ValueError(campo + " debe ser un decimal con punto.")
    try:
        scaled = Decimal(texto) * factor
    except InvalidOperation as error:
        raise ValueError(campo + " no es válido.") from error
    if scaled != scaled.to_integral_value() or scaled < minimo:
        raise ValueError(campo + " fuera de rango o con precisión no admitida.")
    return int(scaled)


def id_fecha(texto, desde, hasta):
    try:
        fecha = date.fromisoformat(texto)
    except ValueError as error:
        raise ValueError("Fecha no válida.") from error
    if fecha.isoformat() != texto or not desde <= fecha <= hasta:
        raise ValueError("Fecha fuera del periodo del lote.")
    return int(fecha.strftime("%Y%m%d"))


def cargar_dimensiones(db, datos, desde, hasta):
    fecha = desde
    while fecha <= hasta:
        db.execute("INSERT INTO dim_fecha VALUES (?, ?, ?, ?, ?)",
                   (int(fecha.strftime("%Y%m%d")), fecha.isoformat(), fecha.year, fecha.month, fecha.day))
        fecha += timedelta(days=1)
    ids = {}
    for nombre, (clave, tabla, campos) in DIMENSIONES.items():
        encontrados = set()
        for fila, row in filas_csv(datos / (nombre + ".csv"), campos):
            if row[clave] in encontrados or not all(row.values()):
                raise ValueError(f"Dimensión vacía o clave repetida en {nombre}.csv, fila {fila}.")
            if not re.fullmatch(r"[A-Z0-9_-]{1,20}", row[clave]) or len(row["nombre"]) > 80:
                raise ValueError(f"Código o nombre inválido en {nombre}.csv, fila {fila}.")
            if "categoria" in row and len(row["categoria"]) > 40:
                raise ValueError(f"Categoría demasiado extensa en {nombre}.csv, fila {fila}.")
            encontrados.add(row[clave])
            marcas = ",".join(["?"] * len(campos))
            db.execute(f"INSERT INTO {tabla} VALUES ({marcas})", tuple(row[campo] for campo in campos))
        ids[clave] = encontrados
    return ids


def validar_claves(row, ids, claves):
    for clave in claves:
        if row[clave] not in ids[clave]:
            raise ValueError(f"Código de {clave} inexistente: {row[clave]}.")


def preparar_venta(row, ids, desde, hasta):
    doc = row["comprobante"]
    if not re.fullmatch(r"[A-Z0-9-]{1,32}", doc):
        raise ValueError("Comprobante vacío o con formato no admitido.")
    if not re.fullmatch(r"[1-9]\d{0,5}", row["linea"]):
        raise ValueError("El número de línea debe ser un entero positivo.")
    numero = int(row["linea"])
    fecha = id_fecha(row["fecha"], desde, hasta)
    validar_claves(row, ids, ("producto", "cliente", "canal"))
    gramos = fijo(row["peso_kg"], 1000, 1, "Peso")
    precio = fijo(row["precio_kg"], 100, 1, "Precio")
    descuento = fijo(row["descuento_soles"], 100, 0, "Descuento")
    bruto = (gramos * precio + 500) // 1000
    if bruto > 9_000_000_000_000_000:
        raise ValueError("Importe fuera del rango entero admitido.")
    if descuento > bruto:
        raise ValueError("Descuento mayor que el importe bruto.")
    valores = (doc, numero, fecha, row["producto"], row["cliente"], row["canal"],
               gramos, precio, bruto, descuento, bruto - descuento)
    return (doc, numero), valores


def preparar_stock(row, ids, desde, hasta):
    fecha = id_fecha(row["fecha"], desde, hasta)
    validar_claves(row, ids, ("producto", "ubicacion"))
    saldo = fijo(row["saldo_kg"], 1000, 0, "Saldo")
    clave = (fecha, row["producto"], row["ubicacion"])
    return clave, (*clave, saldo)


def cargar_hechos(db, datos, ids, desde, hasta):
    fuentes = [
        ("ventas", "hecho_venta", VENTA, ("comprobante", "linea"), preparar_venta),
        ("inventario", "hecho_inventario", STOCK, ("fecha", "producto", "ubicacion"), preparar_stock),
    ]
    for nombre, tabla, campos, claves, preparar in fuentes:
        cont = Counter()
        vistas, incidencias = {}, []
        docs_cabecera = {}
        for fila, row in filas_csv(datos / (nombre + ".csv"), campos):
            cont["extraidas"] += 1
            clave_txt = "/".join(row[c] for c in claves)[:100]
            try:
                pk, valores = preparar(row, ids, desde, hasta)
                if pk in vistas:
                    if vistas[pk] != valores:
                        raise ValueError("Clave repetida con valores distintos; se conserva la primera línea válida.")
                    cont["duplicadas"] += 1
                    incidencias.append((nombre, fila, clave_txt, "Duplicada", "Repetición exacta de una fila válida."))
                    continue
                if nombre == "ventas":
                    doc, fecha, cliente, canal = valores[0], valores[2], valores[4], valores[5]
                    cabecera = (fecha, cliente, canal)
                    if doc in docs_cabecera and docs_cabecera[doc] != cabecera:
                        raise ValueError("La fecha, el cliente o el canal contradicen la cabecera del comprobante.")
                    docs_cabecera[doc] = cabecera
            except ValueError as error:
                cont["rechazadas"] += 1
                incidencias.append((nombre, fila, clave_txt, "Rechazada", str(error)[:160]))
                continue
            marcas = ",".join(["?"] * len(valores))
            db.execute(f"INSERT INTO {tabla} VALUES ({marcas})", valores)
            vistas[pk] = valores
            cont["aceptadas"] += 1
        db.execute("INSERT INTO bitacora_etl VALUES (?,?,?,?,?)",
                   (nombre, cont["extraidas"], cont["aceptadas"], cont["duplicadas"], cont["rechazadas"]))
        db.executemany("INSERT INTO incidencia_etl VALUES (?,?,?,?,?)", incidencias)


def diccionarios(db, sql, nombres):
    return [dict(zip(nombres, fila)) for fila in db.execute(sql)]


def datos_web(db, origen, pruebas):
    productos = diccionarios(db, "SELECT producto_id,nombre,categoria FROM dim_producto ORDER BY producto_id", ("id", "nombre", "categoria"))
    clientes = diccionarios(db, "SELECT cliente_id,nombre FROM dim_cliente ORDER BY cliente_id", ("id", "nombre"))
    canales = diccionarios(db, "SELECT canal_id,nombre FROM dim_canal ORDER BY canal_id", ("id", "nombre"))
    ventas = diccionarios(db, """
        SELECT f.fecha_iso,v.comprobante,v.linea,v.producto_id,v.cliente_id,v.canal_id,v.cantidad_g,
               v.bruto_cent,v.descuento_cent,v.neto_cent
        FROM hecho_venta v JOIN dim_fecha f ON f.fecha_id=v.fecha_id ORDER BY v.fecha_id,v.comprobante,v.linea""",
        ("fecha","comprobante","linea","producto","cliente","canal","gramos","brutoCent","descuentoCent","netoCent"))
    inventario = diccionarios(db, """
        SELECT f.fecha_iso,i.producto_id,u.nombre,i.saldo_g FROM hecho_inventario i
        JOIN dim_fecha f ON i.fecha_id=f.fecha_id JOIN dim_ubicacion u ON i.ubicacion_id=u.ubicacion_id
        ORDER BY f.fecha_iso,i.producto_id,u.ubicacion_id""", ("fecha","producto","ubicacion","gramos"))
    ultima = max(r["fecha"] for r in inventario)
    fuentes = diccionarios(db, "SELECT * FROM bitacora_etl ORDER BY fuente", ("fuente","extraidas","aceptadas","duplicadas","rechazadas"))
    incidencias = diccionarios(db, "SELECT fuente,fila,clave,tipo,motivo FROM incidencia_etl ORDER BY fuente,fila", ("fuente","fila","clave","tipo","motivo"))
    control = next(r.copy() for r in fuentes if r["fuente"] == "ventas")
    control.pop("fuente")
    control.update({
        "netoCent": sum(f["netoCent"] for f in ventas), "gramos": sum(f["gramos"] for f in ventas),
        "stockGramos": sum(f["gramos"] for f in inventario if f["fecha"] == ultima),
        "comprobantes": len({f["comprobante"] for f in ventas}), "controles": pruebas,
        "incidencias": incidencias, "fuentes": fuentes,
    })
    return {
        "meta": {"desde": origen["desde"], "hasta": origen["hasta"], "fechaCorte": ultima,
                 "moneda": "PEN", "demostrativo": True},
        "productos": productos, "canales": canales, "clientes": clientes,
        "ventas": ventas, "inventario": inventario, "control": control,
    }


def literal(valor):
    if valor is None:
        return "NULL"
    return str(valor) if isinstance(valor, int) else "'" + str(valor).replace("'", "''") + "'"


def exportar_postgres(db, sql_modelo, destino):
    with destino.open("w", encoding="utf-8", newline="\n") as out:
        out.write("BEGIN;\nCREATE SCHEMA IF NOT EXISTS naveda_demo;\nSET LOCAL search_path TO naveda_demo, pg_catalog;\n")
        out.write("SELECT pg_advisory_xact_lock(46269131);\n")
        out.write(sql_modelo + "\n")
        for tabla in reversed(TABLAS):
            out.write("DELETE FROM " + tabla + ";\n")
        for tabla in TABLAS:
            filas = db.execute("SELECT * FROM " + tabla)
            nombres = [col[0] for col in filas.description]
            while grupo := filas.fetchmany(150):
                out.write(f"INSERT INTO {tabla} ({', '.join(nombres)}) VALUES\n")
                out.write(",\n".join("(" + ",".join(literal(v) for v in fila) + ")" for fila in grupo) + ";\n")
        out.write("COMMIT;\n")


def huellas(carpeta):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(carpeta.glob("*.csv"))}


def ejecutar(datos, salida, web=None):
    datos = datos.resolve()
    salida.mkdir(parents=True, exist_ok=True)
    inicio = datetime.now(timezone.utc)
    contador = perf_counter()
    huellas_entrada = huellas(datos)
    origen = controles_origen(datos)
    fechas = [origen["desde"], origen["hasta"], *(f for f, u in origen["saldos"])]
    desde, hasta = date.fromisoformat(min(fechas)), date.fromisoformat(max(fechas))
    esquema = (RUTA / "modelo.sql").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(dir=salida, prefix="etl-") as carpeta:
        temporal = Path(carpeta)
        db = sqlite3.connect(temporal / "naveda_demo.sqlite")
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.executescript(esquema)
            with db:
                ids = cargar_dimensiones(db, datos, desde, hasta)
                cargar_hechos(db, datos, ids, desde, hasta)
            pruebas = validar_conciliacion(db, origen)
            fallos = [r["prueba"] for r in pruebas if not r["cumple"]]
            if fallos:
                raise ValueError("Fallaron controles de conciliación: " + ", ".join(fallos))
            modelo = datos_web(db, origen, pruebas)
            exportar_postgres(db, esquema, temporal / "postgresql_demo.sql")
        finally:
            db.close()
        control = modelo["control"]
        payload = json.dumps(modelo, separators=(",", ":"), ensure_ascii=False).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
        (temporal / "demo.js").write_text("window.NAVEDA_DEMO = " + payload + ";\n", encoding="utf-8")
        (temporal / "control.json").write_text(json.dumps(control, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if huellas_entrada != huellas(datos):
            raise ValueError("Los archivos de origen cambiaron durante la carga; repita el proceso.")
        ejecucion = {"demostrativo": True, "inicio_utc": inicio.isoformat(), "fin_utc": datetime.now(timezone.utc).isoformat(),
                     "duracion_ms": round((perf_counter()-contador)*1000, 3),
                     "archivos_sha256": huellas_entrada, "fuentes": control["fuentes"],
                     "pruebas_correctas": len(pruebas), "pruebas_totales": len(pruebas)}
        (temporal / "bitacora_ejecucion.json").write_text(json.dumps(ejecucion, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for nombre in ("naveda_demo.sqlite","postgresql_demo.sql","control.json","bitacora_ejecucion.json","demo.js"):
            os.replace(temporal / nombre, salida / nombre)
    if web:
        web = web.resolve()
        destino = web / "demo.js"
        web.mkdir(parents=True, exist_ok=True)
        if destino.resolve() != (salida / "demo.js").resolve():
            with tempfile.NamedTemporaryFile(dir=web, delete=False) as archivo:
                local = Path(archivo.name)
                archivo.write((salida / "demo.js").read_bytes())
            os.replace(local, destino)
    return control


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Carga y concilia los CSV demostrativos en un Data Mart y exporta la vista web.")
    cli.add_argument("--datos", type=Path, default=RUTA / "datos")
    cli.add_argument("--salida", type=Path, default=RUTA / "salida")
    cli.add_argument("--web", type=Path, help="Carpeta opcional donde actualizar otra copia de demo.js.")
    opciones = cli.parse_args()
    try:
        control = ejecutar(opciones.datos, opciones.salida, opciones.web)
    except (ValueError, OSError, sqlite3.Error) as error:
        cli.exit(1, "Carga interrumpida: " + str(error) + "\n")
    print(f"Ventas: {control['extraidas']} extraídas, {control['aceptadas']} aceptadas, "
          f"{control['duplicadas']} duplicadas y {control['rechazadas']} rechazadas.")
    print(f"Conciliaciones: {len(control['controles'])}/{len(control['controles'])} satisfactorias.")
