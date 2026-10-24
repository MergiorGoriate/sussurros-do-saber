/* The server validates dates and permissions; this only clarifies the editor controls. */
(()=>{
 const box=document.querySelector('[data-article-scheduling]');if(!box)return;
 const form=box.closest('form'),state=form.elements.status,date=form.elements.scheduled_at,zone=form.elements.schedule_timezone,status=document.getElementById('scheduleStatus');
 let previousZone=zone.value;
 const update=()=>{
  const scheduled=state.value==='scheduled';
  date.required=scheduled;date.disabled=!scheduled;zone.disabled=!scheduled;
  status.textContent=scheduled?'Ao guardar, o artigo fica programado no fuso horário seleccionado.':'A data só será aplicada quando seleccionar o estado Programado.';
 };
 zone.addEventListener('change',()=>{
  if(date.value){
   const instant=new Date(date.value+(previousZone==='UTC'?'Z':'+02:00'));
   if(!Number.isNaN(instant.getTime()))date.value=new Date(instant.getTime()+(zone.value==='UTC'?0:7200000)).toISOString().slice(0,16);
  }
  previousZone=zone.value;update();
 });
 state.addEventListener('change',update);update();
})();
