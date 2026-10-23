/* Local charts only: no analytics endpoint, third-party script or visitor identity. */
(()=>{
 'use strict';
 document.querySelectorAll('[data-science-chart]').forEach(root=>{
  const host=root.querySelector('[data-chart]'),status=root.querySelector('[data-chart-status]');
  let data;
  try{data=JSON.parse(root.querySelector('.science-chart-data').textContent);}catch{status.textContent='Não foi possível apresentar o gráfico. Consulte a tabela.';return;}
  const ns='http://www.w3.org/2000/svg';
  function element(name,attributes,text){const node=document.createElementNS(ns,name);Object.entries(attributes).forEach(([k,v])=>node.setAttribute(k,String(v)));if(text!==undefined)node.textContent=text;return node;}
  function draw(key){
   host.replaceChildren();
   const valid=data.filter(row=>typeof row[key]==='number'&&Number.isFinite(row[key])&&row[key]>=0);
   if(!valid.length){status.textContent='Dados insuficientes para apresentar a evolução. Consulte a cobertura de recolha.';return;}
   const label=key==='views'?'visualizações':'downloads';
   const max=Math.max(1,...valid.map(row=>row[key]));
   const svg=element('svg',{viewBox:'0 0 720 210',role:'group','aria-label':'Evolução diária de '+label});
   svg.append(element('text',{x:4,y:15},String(max)),element('text',{x:4,y:178},'0'));
   let segment=[];
   const flush=()=>{if(segment.length)svg.append(element('polyline',{points:segment.join(' ')}));segment=[];};
   data.forEach((row,i)=>{
    if(typeof row[key]!=='number'){flush();return;}
    const x=45+(i/Math.max(1,data.length-1))*650,y=175-(row[key]/max)*145;
    segment.push(x+','+y);
   });flush();
   data.forEach((row,i)=>{
    if(typeof row[key]!=='number')return;
    const circle=element('circle',{cx:45+(i/Math.max(1,data.length-1))*650,cy:175-(row[key]/max)*145,r:4,tabindex:i===data.findIndex(r=>typeof r[key]==='number')?0:-1,role:'button','aria-label':row.day+': '+row[key]+' '+label});
    const show=()=>{status.textContent=row.day+': '+row[key]+' '+label;};
    circle.addEventListener('focus',()=>{svg.querySelectorAll('circle').forEach(c=>c.setAttribute('tabindex',String(c===circle?0:-1)));show();});circle.addEventListener('pointerenter',show);circle.addEventListener('click',show);circle.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();const points=[...svg.querySelectorAll('circle')],at=points.indexOf(circle);const next=event.key==='Home'?0:event.key==='End'?points.length-1:Math.max(0,Math.min(points.length-1,at+(event.key==='ArrowRight'?1:-1)));points[next].focus();}else if(event.key==='Enter'||event.key===' '){event.preventDefault();show();}});svg.append(circle);
   });
   svg.append(element('text',{x:45,y:202},data[0].day),element('text',{x:695,y:202,'text-anchor':'end'},data[data.length-1].day));
   host.append(svg);status.textContent='Evolução de '+label+'. Foque um ponto para consultar o valor; a tabela contém os mesmos dados.';
  }
  root.querySelectorAll('[data-series]').forEach(button=>button.addEventListener('click',()=>{root.querySelectorAll('[data-series]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));draw(button.dataset.series);}));draw('views');
 });
 document.querySelectorAll('[data-metrics-target]').forEach(button=>{
  const panel=document.getElementById(button.dataset.metricsTarget);if(!panel)return;
  button.hidden=false;
  button.addEventListener('click',()=>{panel.open=!panel.open;button.setAttribute('aria-expanded',String(panel.open));if(panel.open){panel.scrollIntoView({block:'start',behavior:'auto'});panel.querySelector('summary').focus();}});
  panel.addEventListener('toggle',()=>button.setAttribute('aria-expanded',String(panel.open)));
 });
})();
