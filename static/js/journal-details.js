(()=>{
 const dialog=document.getElementById('journal-details-dialog');if(!dialog)return;
 const tabs=[...dialog.querySelectorAll('[data-details-tab]')];
 let opener;
 const activate=(name,focus=false)=>{
   tabs.forEach(tab=>{
     const selected=tab.dataset.detailsTab===name;
     tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;
     document.getElementById(tab.getAttribute('aria-controls')).hidden=!selected;
     if(selected&&focus)tab.focus();
   });
   dialog.querySelector('.journal-details-body').scrollTop=0;
 };
 document.querySelectorAll('[data-journal-details]').forEach(button=>button.addEventListener('click',()=>{
   opener=button;
   activate(button.dataset.journalDetails);
   if(button.dataset.journalDetails==='authors'){
     const index=button.dataset.authorIndex||'0';
     dialog.querySelectorAll('[data-details-author]').forEach(card=>{card.open=card.dataset.detailsAuthor===index;});
   }
   if(!dialog.open)dialog.showModal();
   if(button.dataset.journalDetails==='authors'){
     dialog.querySelector('[data-details-author="'+(button.dataset.authorIndex||'0')+'"]')?.scrollIntoView({block:'nearest'});
   }
 }));
 tabs.forEach((tab,index)=>{
   tab.addEventListener('click',()=>activate(tab.dataset.detailsTab));
   tab.addEventListener('keydown',event=>{
     let next;
     if(event.key==='ArrowRight')next=(index+1)%tabs.length;
     else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;
     else if(event.key==='Home')next=0;
     else if(event.key==='End')next=tabs.length-1;
     else return;
     event.preventDefault();activate(tabs[next].dataset.detailsTab,true);
   });
 });
 document.getElementById('journal-details-close').addEventListener('click',()=>dialog.close());
 dialog.addEventListener('close',()=>opener?.focus());
 dialog.addEventListener('click',event=>{
   if(event.target!==dialog)return;
   const bounds=dialog.getBoundingClientRect();
   if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)dialog.close();
 });
})();
