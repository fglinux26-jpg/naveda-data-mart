(function (root) {
  'use strict';
  function crearModelo(datos) {
    const porId = registros => new Map(registros.map(r => [r.id, r]));
    const productos = porId(datos.productos);
    const clientes = porId(datos.clientes);
    const canales = porId(datos.canales);
    const limpiar = texto => String(texto).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    function ventas(f) {
      const consulta = limpiar(f.buscar || '');
      return datos.ventas.filter(v => {
        if (f.desde && v.fecha < f.desde || f.hasta && v.fecha > f.hasta) return false;
        if (f.canal && v.canal !== f.canal || f.producto && v.producto !== f.producto) return false;
        if (f.categoria && productos.get(v.producto).categoria !== f.categoria) return false;
        if (f.cliente && f.cliente !== v.cliente) return false;
        if (!consulta) return true;
        const texto = [v.comprobante, productos.get(v.producto).nombre, clientes.get(v.cliente).nombre, canales.get(v.canal).nombre].join(' ');
        return limpiar(texto).includes(consulta);
      });
    }
    function totales(filas) {
      let netoCent = 0, gramos = 0;
      const documentos = new Set();
      for (const v of filas) {
        netoCent += v.netoCent;
        gramos += v.gramos;
        documentos.add(v.comprobante);
      }
      return {netoCent, gramos, comprobantes: documentos.size, ticketCent: documentos.size ? netoCent / documentos.size : 0};
    }
    function agrupado(filas, clave, campo) {
      const valores = new Map();
      for (const r of filas) {
        const k = clave(r);
        valores.set(k, (valores.get(k) || 0) + r[campo]);
      }
      return [...valores.entries()];
    }
    function inicioSemana(iso) {
      const d = new Date(iso + 'T12:00:00Z');
      d.setUTCDate(d.getUTCDate() - (d.getUTCDay() + 6) % 7);
      return d.toISOString().slice(0, 10);
    }
    function evolucion(filas, paso) {
      const clave = paso === 'mes' ? v => v.fecha.slice(0, 7) + '-01' : v => inicioSemana(v.fecha);
      return agrupado(filas, clave, 'netoCent').sort((a, b) => a[0].localeCompare(b[0]));
    }
    function inventario(f) {
      return datos.inventario.filter(r => (!f.ubicacion || f.ubicacion === r.ubicacion)
        && (!f.categoria || f.categoria === productos.get(r.producto).categoria)
        && (!f.producto || f.producto === r.producto));
    }
    return {productos, clientes, canales, ventas, totales, agrupado, evolucion, inventario};
  }
  root.crearModeloComercial = crearModelo;
  if (typeof module === 'object' && module.exports) module.exports = {crearModelo};
})(typeof window === 'object' ? window : globalThis);
