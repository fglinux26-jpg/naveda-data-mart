import argparse
import csv
import random
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


PRODUCTOS = [
    ("P01", "Lomo fino", "Res", "52.80"),
    ("P02", "Bife ancho", "Res", "39.40"),
    ("P03", "Asado pejerrey", "Res", "31.60"),
    ("P04", "Carne molida", "Res", "23.20"),
    ("P05", "Chuleta de cerdo", "Cerdo", "22.50"),
    ("P06", "Costilla de cerdo", "Cerdo", "25.80"),
    ("P07", "Pierna de cerdo", "Cerdo", "20.40"),
    ("P08", "Pechuga de pollo", "Aves", "18.80"),
    ("P09", "Pierna de pollo", "Aves", "13.60"),
    ("P10", "Pollo entero", "Aves", "11.20"),
]
CANALES = [("MIN", "Minorista"), ("MAY", "Mayorista"), ("INS", "Institucional")]
UBICACIONES = [("U01", "Cámara norte"), ("U02", "Cámara sur")]
INICIO = date(2026, 8, 1)
FIN = date(2026, 10, 31)
CENTESIMA = Decimal("0.01")
MIL = Decimal("1000")


def guardar(path, campos, filas):
    with path.open("w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(campos)
        escritor.writerows(filas)


def soles(valor):
    return format(valor.quantize(CENTESIMA, rounding=ROUND_HALF_UP), ".2f")


def kg(gramos):
    return format(Decimal(gramos) / MIL, ".3f")


def construir(carpeta):
    carpeta.mkdir(parents=True, exist_ok=True)
    rng = random.Random(260826)
    clientes = [(f"C{i:02}", f"Cliente {i:02}") for i in range(1, 19)]
    guardar(carpeta / "productos.csv", ["producto", "nombre", "categoria"], (item[:3] for item in PRODUCTOS))
    guardar(carpeta / "clientes.csv", ["cliente", "nombre"], clientes)
    guardar(carpeta / "canales.csv", ["canal", "nombre"], CANALES)
    guardar(carpeta / "ubicaciones.csv", ["ubicacion", "nombre"], UBICACIONES)

    ventas, comprobantes = [], []
    despacho = defaultdict(lambda: [Decimal(0), 0])
    fecha = INICIO
    secuencia = 0
    while fecha <= FIN:
        cantidad_docs = 2 + rng.randrange(4) + (2 if fecha.weekday() in (4, 5) else 0) + (1 if fecha.month == 10 else 0)
        for _ in range(cantidad_docs):
            secuencia += 1
            canal = rng.choices(["MIN", "MAY", "INS"], weights=(51, 32, 17))[0]
            grupo = {"MIN": clientes[:8], "MAY": clientes[8:14], "INS": clientes[14:]}[canal]
            cliente = rng.choice(grupo)[0]
            codigo = f"FDM-{secuencia:05}"
            lineas = rng.randrange(1, 4)
            neto_doc, peso_doc = Decimal(0), 0
            for numero, (producto, _, _, tarifa) in enumerate(rng.sample(PRODUCTOS, lineas), 1):
                gramos = {"MIN": 250, "MAY": 1000, "INS": 750}[canal] * rng.randint(2, 12)
                precio = Decimal(tarifa)
                bruto = (Decimal(kg(gramos)) * precio).quantize(CENTESIMA, rounding=ROUND_HALF_UP)
                tasa = Decimal(rng.choice([0, 0, 2, 3, 5])) / 100 if canal != "MIN" else Decimal(0)
                descuento = (bruto * tasa).quantize(CENTESIMA, rounding=ROUND_HALF_UP)
                neto = bruto - descuento
                ventas.append([codigo, str(numero), fecha.isoformat(), producto, cliente, canal,
                               kg(gramos), soles(precio), soles(descuento)])
                neto_doc += neto
                peso_doc += gramos
                control = despacho[fecha.strftime("%Y-%m"), producto, canal]
                control[0] += neto
                control[1] += gramos
            comprobantes.append((fecha.isoformat(), codigo, canal, soles(neto_doc), kg(peso_doc)))
        fecha += timedelta(days=1)

    for pos in (8, 94):
        ventas.append(ventas[pos].copy())
    fila_conflictiva = ventas[38].copy()
    fila_conflictiva[6] = kg(int(Decimal(fila_conflictiva[6]) * 1000) + 500)
    ventas.append(fila_conflictiva)
    ejemplo = ventas[0].copy()
    for sufijo, indice, error in (("01", 3, "P99"), ("02", 6, "-1.250"), ("03", 8, "999999.00")):
        fila = ejemplo.copy()
        fila[0] = "OBS-" + sufijo
        fila[indice] = error
        ventas.append(fila)

    campos_venta = ["comprobante", "linea", "fecha", "producto", "cliente", "canal", "peso_kg", "precio_kg", "descuento_soles"]
    guardar(carpeta / "ventas.csv", campos_venta, ventas)
    guardar(carpeta / "control_comprobantes.csv", ["fecha", "comprobante", "canal", "neto_soles", "peso_kg"], comprobantes)
    guardar(carpeta / "control_despacho.csv", ["mes", "producto", "canal", "neto_soles", "peso_kg"],
            ((mes, prod, canal, soles(valores[0]), kg(valores[1])) for (mes, prod, canal), valores in sorted(despacho.items())))

    stock, conteo_fisico = [], defaultdict(int)
    for ubicacion, _ in UBICACIONES:
        for producto, _, _, _ in PRODUCTOS:
            gramos = rng.randint(120, 1300) * 125
            stock.append((FIN.isoformat(), producto, ubicacion, kg(gramos)))
            conteo_fisico[ubicacion] += gramos
    guardar(carpeta / "inventario.csv", ["fecha", "producto", "ubicacion", "saldo_kg"], stock)
    guardar(carpeta / "control_existencias.csv", ["fecha", "ubicacion", "peso_kg"],
            ((FIN.isoformat(), ubicacion, kg(peso)) for ubicacion, peso in sorted(conteo_fisico.items())))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Genera exclusivamente el juego ficticio reproducible del prototipo.")
    cli.add_argument("--datos", type=Path, default=Path(__file__).resolve().parent / "datos")
    construir(cli.parse_args().datos)
