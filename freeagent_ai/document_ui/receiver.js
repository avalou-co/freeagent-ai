(()=>{
  let token=window.location.hash.slice(1);
  // Clear the fragment before any further request. No cookies, storage, analytics
  // or model-visible data carry this one-use delegated capability.
  window.history.replaceState(null,"",window.location.pathname);
  window.addEventListener("DOMContentLoaded",()=>{
    const status=document.getElementById("status"), form=document.getElementById("download-form"), grant=document.getElementById("grant");
    if(!/^[A-Za-z0-9_-]{43}$/.test(token)){status.textContent="This download isn’t available. Try Download PDF again.";return;}
    grant.value=token;token="";
    window.addEventListener("pagehide",()=>{grant.value="";});
    form.submit();
    window.setTimeout(()=>{grant.value="";},0);
  },{once:true});
})();
