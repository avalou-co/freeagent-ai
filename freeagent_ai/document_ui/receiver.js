(()=>{
  let token=window.location.hash.slice(1), objectUrl=null;
  // Clear the one-use authority before fonts, provider requests or navigation.
  window.history.replaceState(null,"",window.location.pathname);
  const controller=new AbortController();
  window.addEventListener("pagehide",()=>{
    token="";controller.abort();
    if(objectUrl)URL.revokeObjectURL(objectUrl);
    objectUrl=null;
  });
  window.addEventListener("DOMContentLoaded",async()=>{
    const main=document.querySelector("main"), title=document.getElementById("title"), status=document.getElementById("status"), detail=document.getElementById("detail"), download=document.getElementById("download");
    function fail(message){main.dataset.state="error";title.textContent="Your PDF isn’t available";status.textContent=message;detail.textContent="Return to your chat and select Download PDF to try again.";}
    window.addEventListener("pageshow",event=>{if(event.persisted){download.hidden=true;download.removeAttribute("href");fail("This download page has been closed.");}});
    if(!/^[A-Za-z0-9_-]{43}$/.test(token)){fail("This download link is missing or has expired.");return;}
    const body=new URLSearchParams({grant:token});token="";
    const timer=setTimeout(()=>controller.abort(),45000);
    try{
      const response=await fetch("/documents/download",{method:"POST",headers:{"Content-Type":"application/x-www-form-urlencoded"},body,credentials:"omit",cache:"no-store",redirect:"error",signal:controller.signal});
      body.delete("grant");
      if(!response.ok||response.headers.get("Content-Type")?.split(";",1)[0]!=="application/pdf")throw Error();
      const name=/^attachment; filename="((?:invoices|estimates|credit_notes)-[0-9]+\.pdf)"$/.exec(response.headers.get("Content-Disposition")||"")?.[1];
      const max=5*1024*1024, length=response.headers.get("Content-Length"), declared=length===null?null:Number(length);
      if(!name||!response.body||(declared!==null&&(!Number.isSafeInteger(declared)||declared<1||declared>max)))throw Error();
      const reader=response.body.getReader(), parts=[];let size=0;
      for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>max){await reader.cancel();throw Error();}parts.push(value);}
      if(controller.signal.aborted||!size||(declared!==null&&size!==declared))throw Error();
      const blob=new Blob(parts,{type:"application/pdf"});
      objectUrl=URL.createObjectURL(blob);
      download.href=objectUrl;download.download=name;download.hidden=false;
      main.dataset.state="ready";title.textContent="Your PDF is ready";
      status.textContent="Your browser will handle saving the file.";
      detail.textContent="If the download doesn’t start, select Download PDF. You can keep this page open until you’re done.";
      // One initial request only. Manual use reuses already received bytes in
      // page memory, never the consumed grant or a new provider request.
      download.click();
    }catch{
      controller.abort();body.delete("grant");
      fail("We couldn’t prepare your PDF. The connection may have changed or the request timed out.");
    }finally{clearTimeout(timer);}
  },{once:true});
})();
