import argparse
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

from etl import RUTA, ejecutar


def estado(carpeta):
    archivos = ["naveda_demo.sqlite", "postgresql_demo.sql", "demo.js", "control.json"]
    huellas = {nombre: hashlib.sha256((carpeta / nombre).read_bytes()).hexdigest() for nombre in archivos}
    with sqlite3.connect(carpeta / "naveda_demo.sqlite") as db:
        ventas = db.execute("SELECT COUNT(*),COUNT(DISTINCT comprobante),SUM(neto_cent),SUM(cantidad_g) FROM hecho_venta").fetchone()
        stock = db.execute("SELECT COUNT(*),SUM(saldo_g) FROM hecho_inventario WHERE fecha_id=(SELECT MAX(fecha_id) FROM hecho_inventario)").fetchone()
    return {"huellas_sha256": huellas, "lineas": ventas[0], "comprobantes": ventas[1],
            "neto_centimos": ventas[2], "venta_gramos": ventas[3], "saldos": stock[0], "inventario_gramos": stock[1]}


def comparar(datos):
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp)
        ejecutar(datos, carpeta)
        inicial = estado(carpeta)
        ejecutar(datos, carpeta)
        final = estado(carpeta)
    return {"demostrativo": True, "prueba": "Recargar dos veces los mismos archivos de origen",
            "primera_carga": inicial, "segunda_carga": final, "cumple": inicial == final}


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Ejecuta la carga dos veces en una carpeta temporal y compara los archivos y las medidas.")
    cli.add_argument("--datos", type=Path, default=RUTA / "datos")
    cli.add_argument("--informe", type=Path, help="Archivo JSON donde guardar el resultado de la prueba.")
    args = cli.parse_args()
    resultado = comparar(args.datos)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2) + "\n"
    if args.informe:
        args.informe.parent.mkdir(parents=True, exist_ok=True)
        args.informe.write_text(texto, encoding="utf-8")
    print(texto)
    raise SystemExit(0 if resultado["cumple"] else 1)
