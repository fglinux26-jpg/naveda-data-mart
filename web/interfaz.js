(function () {
  'use strict';
  const datos = window.NAVEDA_DEMO;
  const $ = id => document.getElementById(id);
  if (!datos) { $('vista').innerHTML = '<p class="error">Falta el archivo de datos. Extrae la carpeta completa del paquete y vuelve a abrir index.html.</p>'; $('exportar').hidden = true; return; }
  const modelo = crearModeloComercial(datos);
  const formato = (n, dec = 0) => new Intl.NumberFormat('es-PE', {minimumFractionDigits:dec, maximumFractionDigits:dec}).format(n);
  const soles = cent => 'S/ ' + formato(cent / 100, 2);
  const kg = (gramos, dec = 3) => formato(gramos / 1000, dec);
  const fecha = iso => iso ? iso.slice(8,10) + '/' + iso.slice(5,7) + '/' + iso.slice(0,4) : '';
  const nombreMes = iso => new Intl.DateTimeFormat('es-PE', {month:'short', timeZone:'UTC'}).format(new Date(iso + 'T12:00:00Z')).replace('.','');
  const html = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const iconos = {
    resumen:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    ventas:'<path d="M5 3h14v18l-2-1.5-2 1.5-3-1.5L9 21l-2-1.5L5 21zM8 8h8M8 12h8M8 16h4"/>',
    inventario:'<path d="m3 7.5 9-4.5 9 4.5v9L12 21l-9-4.5zM3 7.5l9 4.5 9-4.5M12 12v9M7.5 5.3l9 4.5"/>',
    control:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
    exportar:'<path d="M12 3v11m-4-4 4 4 4-4M4 15v5h16v-5"/>',
    dinero:'<path d="m3 17 5-5 4 3 8-9m-6 0h6v6"/>',
    kg:'<path d="M4 19h16l-3-12H7z"/><circle cx="12" cy="7" r="3"/>',
    ticket:'<path d="M3 7h18v4a2 2 0 0 0 0 4v3H3v-3a2 2 0 0 0 0-4zM14 9v7"/>'
  };
  function ico(k) { return '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">' + iconos[k] + '</svg>'; }
  const modulos = {
    resumen:['Resumen','Resumen comercial','Ventas, volumen y principales productos del periodo seleccionado.'],
    ventas:['Ventas','Detalle de ventas','Consulta cada línea de comprobante y exporta las operaciones filtradas.'],
    inventario:['Inventario','Inventario al corte','Saldo físico por producto y cámara al ' + fecha(datos.meta.fechaCorte) + '.'],
    control:['Control de carga','Control de carga','Conciliación y trazabilidad de la carga de demostración.']
  };
  const ventaInicial = () => ({desde:datos.meta.desde,hasta:datos.meta.hasta,canal:'',categoria:'',producto:'',cliente:'',buscar:''});
  const stockInicial = () => ({categoria:'',producto:'',ubicacion:''});
  const estado = {ventas:ventaInicial(), stock:stockInicial(), paso:'semana', pagina:1, modulo:'resumen'};
  const categorias = [...new Set(datos.productos.map(p=>p.categoria))].sort();
  const ubicaciones = [...new Set(datos.inventario.map(r=>r.ubicacion))].sort();
  const etiquetas = palabras => palabras.map(v=>[v,v]);
  const porNombre = coleccion => [...coleccion].sort((a,b)=>a.nombre.localeCompare(b.nombre,'es')).map(o=>[o.id,o.nombre]);
  const select = (id,label,opts,actual,todos) => '<label>' + html(label) + '<select data-filtro="' + id + '"><option value="">' + html(todos) + '</option>' + opts.map(([v,n])=>'<option value="'+html(v)+'"'+(v===actual?' selected':'')+'>'+html(n)+'</option>').join('')+'</select></label>';
  const inputFecha = (id, label, f) => '<label>'+label+'<input data-filtro="'+id+'" type="date" value="'+html(f[id])+'"></label>';
  const botonLimpiar = '<button class="reset" type="button" data-accion="limpiar">Restablecer</button>';
  function filtros() {
    const m = estado.modulo;
    const f = m === 'inventario' ? estado.stock : estado.ventas;
    const prods = porNombre(datos.productos.filter(p=>!f.categoria || p.categoria===f.categoria));
    let salida = '';
    if (m === 'inventario') {
      salida = select('ubicacion','Cámara',etiquetas(ubicaciones),f.ubicacion,'Todas las cámaras') + select('categoria','Categoría',etiquetas(categorias),f.categoria,'Todas las categorías') + select('producto','Producto',prods,f.producto,'Todos los productos');
    } else if (m !== 'control') {
      salida = inputFecha('desde','Desde',f) + inputFecha('hasta','Hasta',f) + select('canal','Canal',porNombre(datos.canales),f.canal,'Todos los canales') + select('categoria','Categoría',etiquetas(categorias),f.categoria,'Todas las categorías') + select('producto','Producto',prods,f.producto,'Todos los productos');
      if (m==='ventas') salida+= select('cliente','Cliente',porNombre(datos.clientes),f.cliente,'Todos los clientes') + '<label class="searchbox">Buscar<input data-filtro="buscar" type="search" placeholder="Comprobante o producto" value="'+html(f.buscar)+'"></label>';
    }
    $('filtros').innerHTML = salida ? salida + botonLimpiar : '';
  }
  function tarjeta(label, valor, detalle, icono) {
    return '<article class="metric"><div class="metric-top">'+html(label)+ico(icono)+'</div><strong>'+html(valor)+'</strong><small>'+html(detalle)+'</small></article>';
  }
  function metricas(filas) {
    const t=modelo.totales(filas);
    return '<div class="cards">'+tarjeta('Venta neta',soles(t.netoCent),'Después de descuentos','dinero')+tarjeta('Volumen vendido',kg(t.gramos)+' kg','Peso de las líneas incluidas','kg')+tarjeta('Comprobantes',formato(t.comprobantes),formato(filas.length)+' líneas de venta','ventas')+tarjeta('Ticket promedio',t.comprobantes?soles(t.ticketCent):'—','Venta neta por comprobante','ticket')+'</div>';
  }
  function panel(titulo,detalle,contenido,accion='') {
    return '<section class="panel"><div class="panel-header"><div><h2>'+html(titulo)+'</h2>'+(detalle?'<p class="pnote quiet">'+html(detalle)+'</p>':'')+'</div>'+accion+'</div>'+contenido+'</section>';
  }
  function tabla(cab,filas,numeros=[]) {
    if(!filas.length)return '<p class="empty">No hay registros que coincidan con estos filtros.</p>';
    const clase = i=>numeros.includes(i)?' class="num"':'';
    return '<div class="scroll"><table><thead><tr>'+cab.map((x,i)=>'<th scope="col"'+clase(i)+'>'+html(x)+'</th>').join('')+'</tr></thead><tbody>'+filas.map(r=>'<tr>'+r.map((v,i)=>'<td'+clase(i)+'>'+html(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';
  }
  function evolucion(filas) {
    const pares=modelo.evolucion(filas,estado.paso);
    const seg='<div class="segment" aria-label="Agrupación del gráfico">'+[['semana','Semanas'],['mes','Meses']].map(([v,t])=>'<button type="button" data-paso="'+v+'" aria-pressed="'+(estado.paso===v)+'">'+t+'</button>').join('')+'</div>';
    if(!pares.length)return panel('Evolución de ventas','', '<p class="empty">No hay ventas en el periodo seleccionado.</p>',seg);
    const alto=Math.max(...pares.map(([,v])=>v/100),1);
    const unidad=alto>100?10**(Math.floor(Math.log10(alto))-1):1;
    const tope=Math.ceil(alto/(4*unidad))*4*unidad;
    const ticks=[4,3,2,1,0].map(n=>'<span>'+formato(tope*n/4)+'</span>').join('');
    const barras=pares.map(([k,v],i)=>{
      const clave=estado.paso==='mes'?nombreMes(k):k.slice(8,10)+' '+nombreMes(k);
      const muestra=pares.length<=7||i%Math.ceil(pares.length/6)===0||i===pares.length-1;
      const desc=(estado.paso==='mes'?'Mes de ':'Semana del ')+(estado.paso==='mes'?nombreMes(k)+' '+k.slice(0,4):fecha(k))+' · '+soles(v);
      return '<div class="baritem" tabindex="0" aria-label="'+html(desc)+'" title="'+html(desc)+'" data-info="'+html(desc)+'"><div class="bar" style="height:'+((v/100)/tope*100).toFixed(3)+'%"></div>'+(muestra?'<span class="tick-label">'+html(clave)+'</span>':'')+'</div>';
    }).join('');
    const descBase='Venta neta en soles. '+(estado.paso==='semana'?'Semanas desde el lunes.':'Agrupación por mes.');
    return panel('Evolución de ventas','Venta neta del periodo', '<div class="chart"><div class="ticks">'+ticks+'</div><div class="barbox">'+barras+'</div></div><p class="chart-info" id="detalle-grafico" data-inicial="'+html(descBase)+'">'+html(descBase)+'</p>',seg);
  }
  function ranking(filas) {
    const pares=modelo.agrupado(filas,v=>v.producto,'netoCent').sort((a,b)=>b[1]-a[1] || a[0].localeCompare(b[0])).slice(0,5);
    const cuerpo=pares.length?'<ol class="rank">'+pares.map(([k,v])=>'<li><div><span>'+html(modelo.productos.get(k).nombre)+'</span><b>'+html(soles(v))+'</b></div><span class="track"><i style="width:'+(100*v/Math.max(pares[0][1],1)).toFixed(2)+'%"></i></span></li>').join('')+'</ol>':'<p class="empty">Sin productos para la selección.</p>';
    return panel('Productos principales','Los cinco con mayor venta neta',cuerpo);
  }
  const ordenarVentas=filas=>[...filas].sort((a,b)=>b.fecha.localeCompare(a.fecha)||b.comprobante.localeCompare(a.comprobante)||a.linea-b.linea);
  function datosVentas(filas, extensa) {
    const cab=['Fecha','Comprobante','Producto','Canal'];
    if(extensa)cab.push('Cliente','Línea','Bruto (S/)','Descuento (S/)');
    cab.push('Peso (kg)','Neto (S/)');
    const celdas=filas.map(v=>{
      const c=[fecha(v.fecha),v.comprobante,modelo.productos.get(v.producto).nombre,modelo.canales.get(v.canal).nombre];
      if(extensa)c.push(modelo.clientes.get(v.cliente).nombre,v.linea,formato(v.brutoCent/100,2),formato(v.descuentoCent/100,2));
      c.push(kg(v.gramos),formato(v.netoCent/100,2));return c;
    });
    return tabla(cab,celdas,extensa?[5,6,7,8,9]:[4,5]);
  }
  function resumen(filas) {
    const mas='<a class="table-link" href="#ventas">Ver todas las ventas</a>';
    return metricas(filas)+'<div class="twocol">'+evolucion(filas)+ranking(filas)+'</div>'+panel('Últimas operaciones','Líneas de comprobante más recientes',datosVentas(ordenarVentas(filas).slice(0,5),false),mas);
  }
  function ventasDetalle(filas) {
    const pag=Math.max(1,Math.ceil(filas.length/15)); estado.pagina=Math.min(estado.pagina,pag);
    const inicio=(estado.pagina-1)*15;
    const botones='<div class="pager"><button type="button" data-pag="-1" '+(estado.pagina===1?'disabled':'')+'>Anterior</button><span>Página '+estado.pagina+' de '+pag+'</span><button type="button" data-pag="1" '+(estado.pagina===pag?'disabled':'')+'>Siguiente</button></div>';
    return metricas(filas)+panel('Operaciones de venta',formato(filas.length)+' líneas seleccionadas',datosVentas(ordenarVentas(filas).slice(inicio,inicio+15),true)+(filas.length?botones:''));
  }
  function inventario() {
    const filas=modelo.inventario(estado.stock);
    const total=filas.reduce((sum,v)=>sum+v.gramos,0);
    const lotes=filas.map(v=>[modelo.productos.get(v.producto).nombre,modelo.productos.get(v.producto).categoria,v.ubicacion,fecha(v.fecha),kg(v.gramos)]).sort((a,b)=>a[0].localeCompare(b[0],'es')||a[2].localeCompare(b[2],'es'));
    const cab='<div class="cards">'+tarjeta('Saldo físico',kg(total)+' kg','Al corte del inventario','kg')+tarjeta('Productos',new Set(filas.map(v=>v.producto)).size,'Con saldo registrado','inventario')+tarjeta('Cámaras',new Set(filas.map(v=>v.ubicacion)).size,'Ubicaciones de almacenamiento','inventario')+tarjeta('Fecha de corte',fecha(datos.meta.fechaCorte),'Instantánea de cierre','control')+'</div>';
    return cab+panel('Existencias por ubicación','Unidad de medida: kilogramos.',tabla(['Producto','Categoría','Cámara','Fecha de corte','Saldo (kg)'],lotes,[4]));
  }
  function control() {
    const c=datos.control;
    const met='<div class="cards">'+tarjeta('Líneas recibidas',c.extraidas,'Archivo de ventas','control')+tarjeta('Líneas cargadas',c.aceptadas,'Claves válidas y únicas','ventas')+tarjeta('Duplicados',c.duplicadas,'Copias exactas descartadas','ventas')+tarjeta('Rechazos',c.rechazadas,'Detalle en incidencias','control')+'</div>';
    const valor=(n,u)=>u==='céntimos'?soles(n):u==='gramos'?kg(n)+' kg':formato(n);
    const pruebas=c.controles.map(p=>[p.prueba,valor(p.esperado,p.unidad),valor(p.obtenido,p.unidad),p.cumple?'Conforme':'Revisar']);
    const incid=c.incidencias.map(r=>[r.fuente,r.fila,r.clave,r.motivo]);
    return met+panel('Pruebas de conciliación','Resultados obtenidos del lote de demostración completo.',tabla(['Prueba','Esperado','Obtenido','Resultado'],pruebas))+panel('Incidencias de carga','Cada incidencia remite a una fila del archivo de origen.',tabla(['Origen','Fila','Clave','Motivo'],incid));
  }
  function filtroVentasEfectivo(){
    const f=estado.ventas;
    return estado.modulo==='resumen'?{...f,cliente:'',buscar:''}:f;
  }
  function mostrar() {
    const m=estado.modulo, f=filtroVentasEfectivo();
    const mal=['resumen','ventas'].includes(m)&&f.desde&&f.hasta&&f.desde>f.hasta;
    $('aviso').innerHTML=mal?'<p class="warning">La fecha «Desde» debe ser anterior o igual a «Hasta».</p>':'';
    $('exportar').disabled=Boolean(mal);
    if(mal){$('vista').replaceChildren();return;}
    const filas=(m==='resumen'||m==='ventas')?modelo.ventas(f):[];
    $('vista').innerHTML=(m==='resumen'?resumen(filas):m==='ventas'?ventasDetalle(filas):m==='inventario'?inventario():control())+'<p class="footer-line">Prototipo académico · Datos ficticios para demostración.</p>';
  }
  function modulo() {
    const slug=location.hash.slice(1);
    estado.modulo=Object.hasOwn(modulos,slug)?slug:'resumen';
    estado.pagina=1;
    const [corto,titulo,desc]=modulos[estado.modulo];
    $('ruta').textContent=corto;$('titulo').textContent=titulo;$('introduccion').textContent=desc;
    $('subtitulo').textContent= estado.modulo==='control'?'VERIFICACIÓN TÉCNICA':estado.modulo==='inventario'?'ALMACÉN':'ANÁLISIS COMERCIAL';
    $('navegacion').innerHTML=Object.entries(modulos).map(([k,[n]])=>'<li><a href="#'+k+'" '+(k===estado.modulo?'aria-current="page"':'')+'>'+ico(k)+'<span>'+html(n)+'</span></a></li>').join('');
    $('exportar').innerHTML=ico('exportar')+'Exportar CSV';
    filtros();mostrar();
  }
  function aplicar(t) {
    const k=t.dataset.filtro;if(!k)return;
    const f=estado.modulo==='inventario'?estado.stock:estado.ventas;
    f[k]=t.value;estado.pagina=1;
    if(k==='categoria'){f.producto='';filtros();}
    mostrar();
  }
  $('filtros').addEventListener('change', e=>aplicar(e.target));
  $('filtros').addEventListener('input', e=>{if(e.target.dataset.filtro==='buscar')aplicar(e.target);});
  $('filtros').addEventListener('click',e=>{
    if(!e.target.closest('[data-accion="limpiar"]'))return;
    if(estado.modulo==='inventario')estado.stock=stockInicial();else estado.ventas=ventaInicial();
    estado.pagina=1;filtros();mostrar();
  });
  $('vista').addEventListener('click',e=>{
    const paso=e.target.closest('[data-paso]'), pag=e.target.closest('[data-pag]');
    if(paso){estado.paso=paso.dataset.paso;mostrar();}
    if(pag&&!pag.disabled){estado.pagina+=Number(pag.dataset.pag);mostrar();}
  });
  for(const ev of ['focusin','mouseover','focusout','mouseout']){
    $('vista').addEventListener(ev,e=>{
      const col=e.target.closest('[data-info]'),nota=$('detalle-grafico');if(!col||!nota)return;
      nota.textContent=['focusin','mouseover'].includes(ev)?col.dataset.info:nota.dataset.inicial;
    });
  }
  function exportar() {
    const m=estado.modulo;
    let filas;
    if(m==='control'){filas=[['Prueba','Unidad','Esperado','Obtenido','Cumple'],...datos.control.controles.map(p=>[p.prueba,p.unidad,p.esperado,p.obtenido,p.cumple?'Sí':'No'])];}
    else if(m==='inventario'){
      filas=[['Fecha de corte','Producto','Categoría','Cámara','Saldo kg'],...modelo.inventario(estado.stock).map(v=>[v.fecha,modelo.productos.get(v.producto).nombre,modelo.productos.get(v.producto).categoria,v.ubicacion,(v.gramos/1000).toFixed(3)])];
    }else{
      filas=[['Fecha','Comprobante','Línea','Producto','Categoría','Cliente','Canal','Peso kg','Bruto PEN','Descuento PEN','Neto PEN'],...ordenarVentas(modelo.ventas(filtroVentasEfectivo())).map(v=>[v.fecha,v.comprobante,v.linea,modelo.productos.get(v.producto).nombre,modelo.productos.get(v.producto).categoria,modelo.clientes.get(v.cliente).nombre,modelo.canales.get(v.canal).nombre,(v.gramos/1000).toFixed(3),(v.brutoCent/100).toFixed(2),(v.descuentoCent/100).toFixed(2),(v.netoCent/100).toFixed(2)])];
    }
    const csv=filas.map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(';')).join('\r\n');
    const enlace=document.createElement('a'),url=URL.createObjectURL(new Blob(['\ufeff'+csv],{type:'text/csv;charset=utf-8'}));
    enlace.href=url;enlace.download='naveda-demo-'+m+'.csv';document.body.append(enlace);enlace.click();enlace.remove();setTimeout(()=>URL.revokeObjectURL(url),3000);
  }
  $('exportar').addEventListener('click',exportar);
  $('corte').textContent='Corte de datos · '+fecha(datos.meta.fechaCorte);
  window.addEventListener('hashchange',modulo);modulo();
})();
