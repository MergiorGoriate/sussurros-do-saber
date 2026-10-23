/* Progressive enhancement only; price, method and consent are verified by the server. */
(()=>{
 const form=document.querySelector('[data-billing-checkout]');if(!form)return;
 const method=form.elements.method,phone=form.querySelector('[data-billing-phone]'),recurring=form.querySelector('[data-billing-recurring]');
 const update=()=>{
  const mobile=['mpesa','emola'].includes(method.value),automatic=method.value==='stripe';
  phone.hidden=!mobile;form.elements.phone.disabled=!mobile;form.elements.phone.required=mobile;
  recurring.hidden=!automatic;form.elements.recurring_consent.disabled=!automatic;form.elements.recurring_consent.required=automatic;
  if(!automatic)form.elements.recurring_consent.checked=false;
 };
 method.addEventListener('change',update);update();
})();
