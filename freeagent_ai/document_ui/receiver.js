(()=>{
  const token=window.location.hash.slice(1);
  // Fragments never reach HTTP request/access logs. Clear it immediately and do
  // not persist it in storage, cookies, analytics or model-visible state.
  window.history.replaceState(null,"",window.location.pathname);
  const status=document.getElementById("status"), grant=document.getElementById("grant"), button=document.getElementById("download");
  if(!/^[A-Za-z0-9_-]{43}$/.test(token)){status.textContent="This offer is missing or invalid. Request a new PDF in ChatGPT.";return;}
  grant.value=token; button.disabled=false;
  document.querySelector("form").addEventListener("submit",()=>{
    button.disabled=true;
    status.textContent="Download requested. If it fails or the offer expires, request a new PDF in ChatGPT.";
    window.addEventListener("pagehide",()=>{grant.value="";button.disabled=true;});
  window.setTimeout(()=>{grant.value="";},0);
  });
  window.addEventListener("pagehide",()=>{grant.value="";button.disabled=true;});
  window.setTimeout(()=>{grant.value="";button.disabled=true;status.textContent="This offer expired. Request a new PDF in ChatGPT.";},120000);
})();
