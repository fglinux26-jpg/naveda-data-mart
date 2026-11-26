import csv
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def leer(archivo):
    with archivo.open(encoding="utf-8-sig", newline="") as datos:
        return list(csv.DictReader(datos))


def controles_origen(carpeta):
    comprobantes = leer(carpeta / "control_comprobantes.csv")
    despacho = leer(carpeta / "control_despacho.csv")
    existencias = leer(carpeta / "control_existencias.csv")
    dias = [r["fecha"] for r in comprobantes]
    if not dias or not existencias:
        raise ValueError("La fuente de control necesita comprobantes y un conteo de inventario.")

    cabeceras = {}
    meses = defaultdict(lambda: [0, 0, 0])
    for venta in comprobantes:
        doc = venta["comprobante"]
        if doc in cabeceras:
            raise ValueError("Comprobante de control repetido: " + doc)
        mes = venta["fecha"][:7]
        neto = int(Decimal(venta["neto_soles"]) * 100)
        gramos = int(Decimal(venta["peso_kg"]) * 1000)
        cabeceras[doc] = {"fecha": venta["fecha"], "canal": venta["canal"], "neto": neto, "gramos": gramos}
        meses[mes][0] += neto
        meses[mes][1] += gramos
        meses[mes][2] += 1

    referencia_despacho = {}
    for fila in despacho:
        clave = (fila["mes"], fila["producto"], fila["canal"])
        if clave in referencia_despacho:
            raise ValueError("Grupo de control repetido: " + str(clave))
        referencia_despacho[clave] = (
            int(Decimal(fila["neto_soles"]) * 100), int(Decimal(fila["peso_kg"]) * 1000)
        )
    referencia_saldos = {}
    for fila in existencias:
        clave = (fila["fecha"], fila["ubicacion"])
        if clave in referencia_saldos:
            raise ValueError("Conteo físico repetido: " + str(clave))
        referencia_saldos[clave] = int(Decimal(fila["peso_kg"]) * 1000)
    return {
        "desde": min(dias), "hasta": max(dias), "meses": dict(sorted(meses.items())),
        "cabeceras": cabeceras, "despacho": referencia_despacho, "saldos": referencia_saldos,
    }


def validar_conciliacion(db, origen):
    resultados = []

    def anotar(prueba, esperado, obtenido, unidad):
        resultados.append({"prueba": prueba, "esperado": esperado, "obtenido": obtenido,
                           "unidad": unidad, "cumple": esperado == obtenido})

    importes = (row for row in db.execute("""
        SELECT v.comprobante, f.fecha_iso, v.canal_id, SUM(v.neto_cent), SUM(v.cantidad_g)
        FROM hecho_venta v JOIN dim_fecha f ON f.fecha_id = v.fecha_id
        GROUP BY v.comprobante, f.fecha_iso, v.canal_id
    """))
    por_doc = {doc: {"fecha": fecha, "canal": canal, "neto": neto, "gramos": gramos}
               for doc, fecha, canal, neto, gramos in importes}
    cabeceras = origen["cabeceras"]
    distintas = sum(cabeceras.get(k) != por_doc.get(k) for k in cabeceras.keys() | por_doc.keys())
    anotar("Comprobantes conciliados con cabeceras", len(cabeceras), len(por_doc), "comprobantes")
    anotar("Diferencias por comprobante", 0, distintas, "comprobantes")

    meses_sql = {mes: (neto, gramos, docs) for mes, neto, gramos, docs in db.execute("""
        SELECT SUBSTR(CAST(f.fecha_iso AS VARCHAR(10)), 1, 7), SUM(v.neto_cent),
               SUM(v.cantidad_g), COUNT(DISTINCT v.comprobante)
        FROM hecho_venta v JOIN dim_fecha f ON f.fecha_id = v.fecha_id
        GROUP BY SUBSTR(CAST(f.fecha_iso AS VARCHAR(10)), 1, 7)
    """)}
    meses = origen["meses"]
    for mes in sorted(meses.keys() | meses_sql.keys()):
        exp, obs = meses.get(mes, [0, 0, 0]), meses_sql.get(mes, [0, 0, 0])
        anotar("Venta neta · " + mes, exp[0], obs[0], "céntimos")
    anotar("Venta neta del periodo", sum(x[0] for x in meses.values()), sum(x[0] for x in meses_sql.values()), "céntimos")
    anotar("Peso vendido del periodo", sum(x[1] for x in meses.values()), sum(x[1] for x in meses_sql.values()), "gramos")

    despacho_sql = {(mes, prod, canal): (neto, kg) for mes, prod, canal, neto, kg in db.execute("""
        SELECT SUBSTR(CAST(f.fecha_iso AS VARCHAR(10)), 1, 7), v.producto_id, v.canal_id,
               SUM(v.neto_cent), SUM(v.cantidad_g)
        FROM hecho_venta v JOIN dim_fecha f ON f.fecha_id = v.fecha_id
        GROUP BY SUBSTR(CAST(f.fecha_iso AS VARCHAR(10)), 1, 7), v.producto_id, v.canal_id
    """)}
    despacho = origen["despacho"]
    diferentes = sum(despacho.get(k) != despacho_sql.get(k) for k in despacho.keys() | despacho_sql.keys())
    anotar("Diferencias por mes, producto y canal", 0, diferentes, "grupos")
    clave_filtro = ("2026-09", "P08", "MAY")
    exp = despacho.get(clave_filtro, (0, 0))
    obs = despacho_sql.get(clave_filtro, (0, 0))
    anotar("Septiembre · pechuga de pollo · mayorista", exp[0], obs[0], "céntimos")
    anotar("Peso · septiembre · pechuga · mayorista", exp[1], obs[1], "gramos")

    saldos_sql = {(fecha, ubic): g for fecha, ubic, g in db.execute("""
        SELECT f.fecha_iso, i.ubicacion_id, SUM(i.saldo_g)
        FROM hecho_inventario i JOIN dim_fecha f ON f.fecha_id=i.fecha_id
        GROUP BY f.fecha_iso, i.ubicacion_id
    """)}
    saldos = origen["saldos"]
    for clave in sorted(saldos.keys() | saldos_sql.keys()):
        anotar("Inventario · " + " · ".join(clave), saldos.get(clave), saldos_sql.get(clave), "gramos")
    anotar("Claves foráneas sin correspondencia", 0, len(db.execute("PRAGMA foreign_key_check").fetchall()), "claves")
    return resultados


if __name__ == "__main__":
    import argparse
    import json
    import sqlite3

    carpeta_script = Path(__file__).resolve().parent
    cli = argparse.ArgumentParser(description="Contrasta el Data Mart con los CSV independientes de cabeceras, despacho e inventario.")
    cli.add_argument("--datos", type=Path, default=carpeta_script / "datos")
    cli.add_argument("--base", type=Path, default=carpeta_script / "salida" / "naveda_demo.sqlite")
    args = cli.parse_args()
    with sqlite3.connect(f"{args.base.resolve().as_uri()}?mode=ro", uri=True) as base:
        resultados = validar_conciliacion(base, controles_origen(args.datos))
    print(json.dumps(resultados, indent=2, ensure_ascii=False))
    raise SystemExit(0 if all(x["cumple"] for x in resultados) else 1)
